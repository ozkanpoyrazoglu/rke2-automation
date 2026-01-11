"""
DeepSeek R1 Analysis via Amazon Bedrock
Sends preflight check data to DeepSeek R1 for upgrade readiness analysis
"""

import json
import re
import os
import logging
from typing import Dict, Any, Tuple
import boto3
from botocore.exceptions import ClientError

from app.services.preflight.analysis_schema import AnalysisResult


logger = logging.getLogger(__name__)


class DeepSeekBedrockAnalyzer:
    """Analyzes preflight data using DeepSeek R1 via Amazon Bedrock"""

    SYSTEM_PROMPT = """You are a Senior RKE2 SRE. Analyze the provided Pre-flight Check Data for upgrade readiness.

Output Format: ONLY raw JSON. No markdown, no conversational text outside the JSON.
Structure:
{
  "verdict": "GO" | "NO-GO" | "CAUTION",
  "reasoning_summary": "Concise summary.",
  "findings": {
    "os_layer": ["Finding 1", "Finding 2", ...],
    "etcd_health": ["Finding 1", ...],
    "kubernetes_layer": ["Finding 1", ...],
    "network_layer": ["Finding 1", ...],
    "workload_safety": ["Finding 1", ...]
  },
  "blockers": ["Critical issues"],
  "risks": ["Warnings"],
  "action_plan": ["Steps to fix"]
}

IMPORTANT: The "findings" section must include specific observations for each layer:
- os_layer: Disk space, memory pressure, system load, swap, time drift, internet connectivity
- etcd_health: Leader status, DB size, raft lag, defragmentation needs
- kubernetes_layer: Node readiness, pod crashes, deprecated APIs, PDBs, admission webhooks
- network_layer: CNI version, ingress controller, network health
- workload_safety: HostPath volumes, StatefulSets with local PVs

Core Logic:
- CRITICAL checks -> NO-GO
- Unhealthy Etcd -> NO-GO
- Multiple WARNs -> CAUTION
- CrashLoopBackOff pods -> NO-GO
- Certificates expiring <30 days -> CAUTION
- Disk space <20% on /var/lib/rancher/rke2 or / -> CRITICAL -> NO-GO
- Swap enabled -> CAUTION (best practice violation)
- Time drift >500ms -> CAUTION
- OOM events -> WARN
- Admission webhooks with Fail policy -> CAUTION (may block upgrade)
- High system load (load_1min > cpu_count * 2) -> WARN
- Memory pressure >90% -> CRITICAL, >80% -> WARN
- Deprecated APIs detected -> CRITICAL (must migrate before upgrade)
- Restrictive PodDisruptionBudgets (minAvailable=100% or maxUnavailable=0) -> WARN (may block drain)
- High etcd raft lag (>1000) -> WARN (slow disk I/O)
- Etcd DB size >2GB -> WARN (recommend defrag)
- Error patterns in RKE2 logs -> WARN

Target Version Compatibility (if target_version provided):
- Check if OS/Kernel versions are compatible with target RKE2 version
- RKE2 1.30+ requires Ubuntu 20.04+, RHEL 8+, or equivalent
- Kubernetes 1.25+ removed PodSecurityPolicy - flag if found
- Kubernetes 1.26+ removed v1beta1 HorizontalPodAutoscaler
- Compare deprecated APIs against target version's removal list

Analyze ALL checks in the data and provide actionable, specific recommendations."""

    def __init__(self):
        """Initialize Bedrock client"""
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.model_id = os.getenv("BEDROCK_MODEL_ID")

        if not self.model_id:
            raise ValueError("BEDROCK_MODEL_ID environment variable not set")

        self.bedrock = boto3.client(
            service_name="bedrock-runtime",
            region_name=self.region
        )

    def _optimize_payload(self, preflight_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Optimize preflight data payload for AI by removing non-essential fields.
        Reduces token usage while preserving critical information for analysis.

        Args:
            preflight_data: Full preflight report

        Returns:
            Optimized payload with reduced verbosity
        """
        optimized = preflight_data.copy()

        # Remove very long lists of healthy pod names (keep only problematic ones)
        if "kubernetes" in optimized:
            k8s = optimized["kubernetes"]

            # Keep only pods with high restart counts (>10)
            if "kube_system_pod_restarts" in k8s:
                k8s["kube_system_pod_restarts"] = {
                    name: count for name, count in k8s["kube_system_pod_restarts"].items()
                    if count > 10
                }

            # Limit hostpath_workloads to first 20 (avoid overwhelming)
            if "hostpath_workloads" in k8s and len(k8s["hostpath_workloads"]) > 20:
                k8s["hostpath_workloads"] = k8s["hostpath_workloads"][:20]

            # Limit statefulsets to first 20
            if "statefulsets" in k8s and len(k8s["statefulsets"]) > 20:
                k8s["statefulsets"] = k8s["statefulsets"][:20]

        # Remove full environment variables from checks (if any)
        if "checks" in optimized:
            for check in optimized["checks"]:
                raw_data = check.get("raw_data", {})

                # Remove env vars if present
                if "env" in raw_data:
                    del raw_data["env"]

                # Limit log lines to first 10 lines per error
                if "errors" in raw_data:
                    for error in raw_data["errors"]:
                        if "context_lines" in error and len(error["context_lines"]) > 10:
                            error["context_lines"] = error["context_lines"][:10]

        # Limit certificates to first 15 (only most critical ones)
        if "certificates" in optimized and len(optimized["certificates"]) > 15:
            # Sort by days_until_expiry (most urgent first)
            optimized["certificates"] = sorted(
                optimized["certificates"],
                key=lambda c: c.get("days_until_expiry", 999)
            )[:15]

        return optimized

    def _build_payload(self, preflight_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build Bedrock invoke payload for DeepSeek R1

        Args:
            preflight_data: Preflight report JSON

        Returns:
            Bedrock API payload
        """
        # Optimize payload to reduce token usage
        optimized_data = self._optimize_payload(preflight_data)

        # Extract target version for enhanced context
        target_version = optimized_data.get("cluster_metadata", {}).get("target_version")
        current_version = optimized_data.get("cluster_metadata", {}).get("rke2_version", "unknown")

        # Build enhanced prompt with target version context
        version_context = ""
        if target_version:
            version_context = f"""

**UPGRADE CONTEXT:**
- Current RKE2 Version: {current_version}
- Target RKE2 Version: {target_version}
- **CRITICAL:** Analyze compatibility between current and target versions
- Check for deprecated APIs that will be removed in target version
- Verify OS/Kernel compatibility with target RKE2 version
- Assess if PodDisruptionBudgets will block the upgrade process
"""
        else:
            version_context = f"""

**GENERAL READINESS CHECK:**
- Current RKE2 Version: {current_version}
- No target version specified - perform general health assessment
"""

        # Format prompt for DeepSeek R1 (Llama-style)
        json_data = json.dumps(optimized_data, indent=2)
        prompt = f"<|begin_of_sentence|><|User|>{self.SYSTEM_PROMPT}{version_context}\n\nDATA:\n{json_data}<|Assistant|>"

        return {
            "prompt": prompt,
            "max_gen_len": 2048,
            "temperature": 0.6,
            "top_p": 0.9
        }

    def _parse_deepseek_response(self, response_text: str) -> Dict[str, Any]:
        """Parse DeepSeek R1 response, stripping <think> blocks

        DeepSeek R1 often returns: <think>...reasoning...</think> {json_output}
        We need to extract only the JSON part.

        Args:
            response_text: Raw response from DeepSeek R1

        Returns:
            Parsed JSON dict

        Raises:
            ValueError: If JSON parsing fails
        """
        # Strip <think>...</think> blocks if present
        cleaned = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
        cleaned = cleaned.strip()

        # Try to extract JSON if wrapped in markdown code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(1)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error. Raw response length: {len(response_text)}")
            logger.error(f"Cleaned text: {cleaned[:500]}...")
            logger.error(f"Check if <think> block was stripped: {'<think>' in response_text}")
            raise ValueError(f"Failed to parse JSON from DeepSeek response: {e}")

    def analyze(self, preflight_data: Dict[str, Any]) -> Tuple[AnalysisResult, str, int]:
        """Analyze preflight check data using DeepSeek R1

        Args:
            preflight_data: Preflight report dict (from PreflightCollector)

        Returns:
            Tuple of (AnalysisResult, model_id, token_count)

        Raises:
            ClientError: Bedrock API error
            ValueError: Response parsing error
        """
        try:
            # Build payload
            payload = self._build_payload(preflight_data)

            # Invoke Bedrock
            logger.info(f"Invoking Bedrock model: {self.model_id}")
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                body=json.dumps(payload)
            )

            # Parse response
            response_body = json.loads(response['body'].read())

            # Extract token usage if available
            input_tokens = 0
            output_tokens = 0

            # Try to get token counts from response metadata
            if "usage" in response_body:
                input_tokens = response_body["usage"].get("prompt_tokens", 0)
                output_tokens = response_body["usage"].get("completion_tokens", 0)
            elif "amazon-bedrock-invocationMetrics" in response.get("ResponseMetadata", {}).get("HTTPHeaders", {}):
                # Some models report metrics in headers
                metrics = response["ResponseMetadata"]["HTTPHeaders"].get("amazon-bedrock-invocationMetrics", {})
                input_tokens = metrics.get("inputTokenCount", 0)
                output_tokens = metrics.get("outputTokenCount", 0)

            total_tokens = input_tokens + output_tokens
            logger.info(f"Token usage - Input: {input_tokens}, Output: {output_tokens}, Total: {total_tokens}")

            # Extract generated text (varies by model provider)
            # DeepSeek on Bedrock typically returns: {"generation": "..."}
            # or {"outputs": [{"text": "..."}]}
            generated_text = None

            if "generation" in response_body:
                generated_text = response_body["generation"]
            elif "outputs" in response_body and len(response_body["outputs"]) > 0:
                generated_text = response_body["outputs"][0].get("text")
            elif "completions" in response_body and len(response_body["completions"]) > 0:
                generated_text = response_body["completions"][0].get("data", {}).get("text")
            else:
                # Fallback: log entire response structure
                logger.error(f"Unexpected response structure: {list(response_body.keys())}")
                raise ValueError(f"Cannot find generated text in response. Keys: {list(response_body.keys())}")

            if not generated_text:
                raise ValueError("Empty response from DeepSeek model")

            # Parse DeepSeek-specific response format
            parsed_json = self._parse_deepseek_response(generated_text)

            # Validate and return as tuple with metrics
            analysis_result = AnalysisResult(**parsed_json)
            return (analysis_result, self.model_id, total_tokens)

        except ClientError as e:
            logger.error(f"Bedrock API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            raise
