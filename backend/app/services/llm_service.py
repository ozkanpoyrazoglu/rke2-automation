import boto3
import json
import os

BEDROCK_MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"

UPGRADE_SUMMARY_PROMPT = """You are analyzing an RKE2 cluster upgrade readiness assessment.

Given the following structured readiness check results, provide a concise executive summary focusing on:
- Critical blockers that MUST be resolved before upgrade
- Warnings that should be addressed
- Recommended preparation steps
- Overall go/no-go recommendation

DO NOT make the upgrade decision - only summarize findings and provide recommendations.

Readiness Check Results:
{readiness_json}

Provide your summary in markdown format with clear sections:
## Summary
## Blockers
## Warnings
## Recommendations
## Overall Assessment
"""

def generate_upgrade_summary(readiness_json: dict) -> str:
    """
    Use AWS Bedrock (Claude) to generate upgrade readiness summary
    """
    try:
        bedrock = boto3.client(
            service_name="bedrock-runtime",
            region_name=os.getenv("AWS_REGION", "us-east-1")
        )

        prompt = UPGRADE_SUMMARY_PROMPT.format(
            readiness_json=json.dumps(readiness_json, indent=2)
        )

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2000,
            "temperature": 0.3,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }

        response = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps(request_body)
        )

        response_body = json.loads(response["body"].read())
        summary = response_body["content"][0]["text"]

        return summary

    except Exception as e:
        # Fallback to simple text summary if Bedrock fails
        return f"""# Upgrade Readiness Summary

**Error generating LLM summary:** {str(e)}

## Raw Results
Overall Ready: {readiness_json.get('ready', False)}

### Checks:
{json.dumps(readiness_json.get('checks', {}), indent=2)}
"""
