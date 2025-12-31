# LLM Prompt for Upgrade Readiness Summary

## Prompt Template

```
You are analyzing an RKE2 cluster upgrade readiness assessment.

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
```

## Example LLM Response

```markdown
## Summary

The production-cluster is **NOT READY** for upgrade from v1.27.10+rke2r1 to v1.28.5+rke2r1.
Two critical issues must be resolved before proceeding.

## Blockers

1. **Node Availability**: Worker-3 is in NotReady state
   - Impact: Cluster capacity reduced, workloads may be affected
   - Action: Investigate and restore worker-3 before upgrade

2. **Deprecated API Usage**: 3 resources using deprecated APIs
   - **PodSecurityPolicy (policy/v1beta1)**: Removed in Kubernetes 1.25+
     - Action: Migrate to Pod Security Standards before upgrade
   - **Ingress (networking.k8s.io/v1beta1)**: Replace with networking.k8s.io/v1
   - **CronJob (batch/v1beta1)**: Replace with batch/v1

## Warnings

None - all other checks passed successfully.

## Recommendations

### Pre-Upgrade Checklist

1. **Resolve worker-3 node issue**
   - Check node logs: `kubectl describe node worker-3`
   - Verify kubelet status on the node
   - Ensure node meets resource requirements

2. **Migrate deprecated APIs**
   ```bash
   # Identify all affected resources
   kubectl get ingress,cronjob,psp --all-namespaces -o yaml

   # Update manifests to use current API versions
   # Remove PodSecurityPolicy and implement Pod Security Standards
   ```

3. **Backup before upgrade**
   - etcd snapshot
   - Application data backups
   - Document current state

4. **Plan maintenance window**
   - Estimated downtime: 30-60 minutes
   - Schedule during low-traffic period
   - Notify stakeholders

5. **Staged rollout**
   - Test upgrade on staging environment first
   - Upgrade control plane nodes sequentially
   - Upgrade worker nodes in batches

## Overall Assessment

**DO NOT PROCEED** with upgrade until:
- ✗ Worker-3 is restored to Ready state
- ✗ All deprecated APIs are migrated to supported versions

**Safe to proceed** after above items are resolved:
- ✓ etcd cluster is healthy
- ✓ Sufficient disk space on all nodes
- ✓ Certificates valid for >90 days

Estimated effort to resolve blockers: 4-8 hours
```

## Key Principles

1. **Deterministic checks provide data**: etcd health, node status, disk usage, cert expiry, API deprecations
2. **LLM provides context**: Explains impact, prioritizes issues, recommends specific actions
3. **Human makes decision**: Final go/no-go based on LLM summary + business requirements
4. **No automation**: LLM does NOT trigger upgrades or make decisions
