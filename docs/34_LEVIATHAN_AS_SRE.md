# Leviathan as SRE

**Last Updated:** 2026-01-31  
**Status:** Canonical (Vision)

---

## Overview

Leviathan's long-term vision extends beyond task automation to **autonomous Site Reliability Engineering (SRE)**. This document outlines how Leviathan evolves from executing predefined tasks to monitoring, detecting, and remediating issues autonomously.

**Vision:** Leviathan becomes the SRE that never sleeps—monitoring systems, detecting anomalies, and creating remediation PRs automatically.

---

## Evolution Path

### Phase 1: Task Executor (Current)

**Capabilities:**
- Executes predefined tasks from backlogs
- Creates PRs for documentation, tests, dependencies
- No monitoring or detection capabilities

**Limitations:**
- Reactive only (requires human-defined tasks)
- No awareness of system health
- No autonomous remediation

---

### Phase 2: Self-SRE (Next)

**Capabilities:**
- Monitors Leviathan's own health
- Detects anomalies in Leviathan operations
- Creates remediation PRs for Leviathan issues
- Self-healing within policy bounds

**Examples:**

1. **Disk Space Remediation**
   - **Detection:** Event store disk usage >80%
   - **Action:** Create task to implement event retention policy
   - **PR:** Add cron job to prune events older than 90 days

2. **Failed Worker Recovery**
   - **Detection:** Worker job fails 3 times with same error
   - **Action:** Create task to fix root cause
   - **PR:** Update worker timeout or fix path validation bug

3. **Dependency Updates**
   - **Detection:** Security vulnerability in Python dependency
   - **Action:** Create task to update requirements.txt
   - **PR:** Bump vulnerable package to patched version

4. **Configuration Drift**
   - **Detection:** Deployed manifest differs from Git
   - **Action:** Create task to sync configuration
   - **PR:** Update manifest to match deployed state

**Implementation:**

```python
# leviathan/sre/self_monitor.py

class SelfMonitor:
    """Monitors Leviathan health and creates remediation tasks."""
    
    def check_disk_usage(self):
        usage = get_disk_usage("/data/events")
        if usage > 0.8:
            self.create_remediation_task(
                title="Implement event retention policy",
                scope="core",
                allowed_paths=["leviathan/control_plane/retention.py"],
                acceptance_criteria=[
                    "Delete events older than 90 days",
                    "Run daily via cron",
                    "Log retention actions"
                ]
            )
    
    def check_worker_failures(self):
        failures = get_recent_failures(hours=24)
        if len(failures) >= 3:
            common_error = find_common_error(failures)
            self.create_remediation_task(
                title=f"Fix recurring worker error: {common_error}",
                scope="core",
                allowed_paths=["leviathan/executor/"],
                acceptance_criteria=[
                    f"Resolve error: {common_error}",
                    "Add unit test to prevent regression"
                ]
            )
```

**Guardrails:**
- Self-remediation tasks follow same policy as regular tasks
- No direct commits (PR-based only)
- Human review required for all changes
- Circuit breaker prevents infinite remediation loops

---

### Phase 3: Customer Workload SRE (Future)

**Capabilities:**
- Monitors customer applications and infrastructure
- Detects anomalies, errors, and performance issues
- Creates remediation PRs for customer repos
- Executes runbooks as backlog tasks

**Examples:**

1. **Application Error Spike**
   - **Detection:** Error rate >5% for 10 minutes
   - **Analysis:** Parse logs, identify root cause
   - **Action:** Create task to fix bug
   - **PR:** Fix null pointer exception in API handler

2. **Performance Degradation**
   - **Detection:** API latency >500ms (p95)
   - **Analysis:** Identify slow database query
   - **Action:** Create task to add index
   - **PR:** Add index on frequently queried column

3. **Infrastructure Drift**
   - **Detection:** Terraform state differs from deployed
   - **Action:** Create task to sync state
   - **PR:** Update Terraform to match deployed infrastructure

4. **Security Vulnerability**
   - **Detection:** CVE published for dependency
   - **Action:** Create task to update dependency
   - **PR:** Bump vulnerable package, run security scan

5. **Certificate Expiration**
   - **Detection:** TLS certificate expires in 7 days
   - **Action:** Create task to renew certificate
   - **PR:** Update certificate in Kubernetes secret

**Implementation:**

```python
# leviathan/sre/customer_monitor.py

class CustomerMonitor:
    """Monitors customer workloads and creates remediation tasks."""
    
    def check_error_rate(self, target):
        error_rate = get_error_rate(target, minutes=10)
        if error_rate > 0.05:
            logs = get_recent_error_logs(target, count=100)
            root_cause = analyze_errors(logs)
            
            self.create_remediation_task(
                target=target,
                title=f"Fix error spike: {root_cause.summary}",
                scope="core",
                allowed_paths=[root_cause.file_path],
                acceptance_criteria=[
                    f"Fix {root_cause.error_type}",
                    "Add error handling",
                    "Add unit test"
                ]
            )
    
    def check_performance(self, target):
        latency = get_api_latency_p95(target, minutes=10)
        if latency > 500:
            slow_queries = identify_slow_queries(target)
            
            self.create_remediation_task(
                target=target,
                title="Optimize slow database queries",
                scope="infra",
                allowed_paths=["migrations/"],
                acceptance_criteria=[
                    "Add index on slow query columns",
                    "Verify latency improvement"
                ]
            )
```

---

## Monitoring Integration

### Data Sources

**Leviathan Internal:**
- Control plane event store
- Scheduler logs
- Worker job status
- Spider Node metrics

**Customer Workloads:**
- Application logs (CloudWatch, Datadog)
- Metrics (Prometheus, CloudWatch)
- Traces (Jaeger, X-Ray)
- Alerts (PagerDuty, Opsgenie)

**Infrastructure:**
- Kubernetes events
- AWS CloudWatch
- Terraform state
- GitHub Actions status

### Detection Strategies

**1. Threshold-Based**
- Error rate >5%
- Latency >500ms (p95)
- Disk usage >80%
- Memory usage >90%

**2. Anomaly Detection**
- ML-based anomaly detection
- Baseline comparison
- Seasonal patterns
- Sudden spikes or drops

**3. Pattern Matching**
- Log pattern analysis
- Error message clustering
- Stack trace similarity

**4. Correlation**
- Multiple signals indicating same issue
- Deployment correlation
- Dependency correlation

---

## Remediation Strategies

### 1. Runbook Execution

**Concept:** Encode operational runbooks as backlog tasks.

**Example Runbook:**
```yaml
# .leviathan/runbooks/restart-service.yaml

id: restart-service
title: Restart service on high memory usage
trigger:
  metric: memory_usage_percent
  threshold: 90
  duration: 5m

steps:
  - id: check-memory
    command: kubectl top pod -n production -l app=myapp
    
  - id: restart-deployment
    command: kubectl rollout restart deployment myapp -n production
    
  - id: verify-health
    command: kubectl rollout status deployment myapp -n production
    
  - id: create-incident-report
    scope: docs
    allowed_paths:
      - docs/incidents/
    acceptance_criteria:
      - Document memory spike
      - Include metrics and logs
      - Add remediation steps
```

**Execution:**
- Leviathan detects trigger condition
- Creates task from runbook
- Executes steps sequentially
- Creates PR with incident report

---

### 2. Code Generation

**Concept:** Generate code fixes based on error analysis.

**Example:**
```python
# Error detected: NullPointerException in UserService.java line 42

# Analysis:
# - user.getEmail() called without null check
# - Occurs when user object is null

# Generated fix:
def generate_fix(error):
    return """
    // Before:
    String email = user.getEmail();
    
    // After:
    String email = (user != null) ? user.getEmail() : "unknown";
    """
```

**Guardrails:**
- Generated code must pass CI checks
- Human review required
- Rollback plan documented

---

### 3. Configuration Updates

**Concept:** Update configuration files to resolve issues.

**Examples:**
- Increase memory limits in Kubernetes
- Add retry logic to service configuration
- Update timeout values
- Enable feature flags

---

### 4. Infrastructure Changes

**Concept:** Modify infrastructure as code to resolve issues.

**Examples:**
- Add database index (Terraform)
- Scale up instance size (CloudFormation)
- Add CDN cache rule (Terraform)
- Update security group rules (Terraform)

---

## Safety Mechanisms

### 1. Policy Enforcement

**All remediation tasks must:**
- Specify `allowed_paths` (no unbounded scope)
- Have clear acceptance criteria
- Follow target policy guardrails
- Be delivered via PR (no direct commits)

### 2. Human Review

**Required for:**
- All code changes
- Infrastructure modifications
- Security-related updates
- High-risk remediations

**Optional (auto-merge) for:**
- Documentation updates
- Test additions
- Dependency updates (non-breaking)
- Configuration tweaks (low-risk)

### 3. Rollback Plan

**Every remediation PR must include:**
- Clear description of issue
- Root cause analysis
- Remediation steps
- Rollback procedure
- Testing evidence

### 4. Circuit Breaker

**Prevents infinite loops:**
- Max 3 remediation attempts per issue
- Cooldown period after failures
- Escalate to human after threshold

---

## Use Cases

### Use Case 1: Disk Space Management

**Scenario:** Event store disk usage reaches 85%.

**Detection:**
```python
disk_usage = get_disk_usage("/data/events")
if disk_usage > 0.85:
    trigger_remediation("disk-space-critical")
```

**Remediation Task:**
```yaml
id: implement-event-retention
title: Implement event retention policy
scope: core
priority: high
ready: true
allowed_paths:
  - leviathan/control_plane/retention.py
  - ops/k8s/control-plane.yaml
acceptance_criteria:
  - Delete events older than 90 days
  - Run daily via CronJob
  - Log retention actions
  - Verify disk usage drops below 70%
```

**PR Created:**
- Add `retention.py` module
- Add CronJob manifest
- Update control plane to run retention
- Add unit tests

**Outcome:** Disk usage drops to 60%, issue resolved.

---

### Use Case 2: Dependency Vulnerability

**Scenario:** CVE-2024-1234 published for `requests==2.28.0`.

**Detection:**
```python
vulnerabilities = scan_dependencies("requirements.txt")
if vulnerabilities:
    for vuln in vulnerabilities:
        trigger_remediation("dependency-vulnerability", vuln)
```

**Remediation Task:**
```yaml
id: fix-cve-2024-1234
title: Update requests to fix CVE-2024-1234
scope: deps
priority: high
ready: true
allowed_paths:
  - requirements.txt
acceptance_criteria:
  - Update requests to >=2.31.0
  - Run security scan
  - Verify no breaking changes
```

**PR Created:**
- Update `requirements.txt`
- Run `pip-audit` in CI
- Document vulnerability and fix

**Outcome:** Vulnerability patched, security scan passes.

---

### Use Case 3: API Error Spike

**Scenario:** Customer API error rate spikes to 15%.

**Detection:**
```python
error_rate = get_error_rate("customer-api", minutes=10)
if error_rate > 0.05:
    logs = get_error_logs("customer-api", count=100)
    root_cause = analyze_errors(logs)
    trigger_remediation("api-error-spike", root_cause)
```

**Root Cause:** `NullPointerException` in `UserController.java` line 42.

**Remediation Task:**
```yaml
id: fix-user-controller-npe
title: Fix NullPointerException in UserController
scope: core
priority: critical
ready: true
allowed_paths:
  - src/main/java/com/example/UserController.java
  - src/test/java/com/example/UserControllerTest.java
acceptance_criteria:
  - Add null check for user object
  - Add unit test for null user case
  - Verify error rate drops below 1%
```

**PR Created:**
- Add null check in `UserController.java`
- Add unit test
- Document fix

**Outcome:** Error rate drops to 0.5%, issue resolved.

---

## Metrics and KPIs

### Self-SRE Metrics

- **Self-Healing Rate:** % of Leviathan issues resolved autonomously
- **MTTR (Mean Time to Remediation):** Time from detection to PR merge
- **Remediation Success Rate:** % of remediation PRs that resolve issue
- **False Positive Rate:** % of remediations that were unnecessary

### Customer Workload SRE Metrics

- **Issues Detected:** Count of anomalies/errors detected
- **Issues Remediated:** Count of issues resolved via PR
- **Customer MTTR:** Time from issue detection to resolution
- **Customer Satisfaction:** Feedback on remediation quality

---

## Roadmap

### Phase 1: Self-SRE (Q2 2026)

**Deliverables:**
- Disk space monitoring and retention
- Dependency vulnerability scanning
- Failed worker analysis and remediation
- Configuration drift detection

**Success Criteria:**
- 50% of Leviathan issues self-remediated
- MTTR <1 hour for critical issues

---

### Phase 2: Customer Workload SRE (Q3-Q4 2026)

**Deliverables:**
- Application log monitoring
- Performance anomaly detection
- Error spike remediation
- Runbook execution

**Success Criteria:**
- 10+ customers using SRE features
- 30% of customer issues auto-remediated
- Customer MTTR <2 hours

---

### Phase 3: Advanced SRE (2027)

**Deliverables:**
- ML-based anomaly detection
- Predictive remediation (fix before failure)
- Multi-service correlation
- Incident management integration

**Success Criteria:**
- 80% of issues detected before customer impact
- 50% of issues auto-remediated
- 99.9% uptime for customer workloads

---

## Challenges and Risks

### Challenge 1: False Positives

**Risk:** Leviathan creates unnecessary remediation PRs.

**Mitigation:**
- Tune detection thresholds
- Require multiple signals for confirmation
- Human review for high-risk changes
- Feedback loop to improve detection

### Challenge 2: Incorrect Remediation

**Risk:** Leviathan's fix makes the problem worse.

**Mitigation:**
- Require CI checks to pass
- Rollback plan in every PR
- Circuit breaker prevents repeated failures
- Human review for critical systems

### Challenge 3: Alert Fatigue

**Risk:** Too many remediation PRs overwhelm operators.

**Mitigation:**
- Prioritize critical issues
- Batch low-priority remediations
- Auto-merge low-risk changes
- Configurable alert thresholds

### Challenge 4: Security

**Risk:** Leviathan could be exploited to inject malicious code.

**Mitigation:**
- Strict policy enforcement
- Code review required
- Audit logs for all remediations
- Secrets rotation
- Least-privilege access

---

## Comparison to Traditional SRE

| Aspect | Traditional SRE | Leviathan SRE |
|--------|----------------|---------------|
| **Detection** | Manual monitoring, alerts | Automated monitoring, ML-based |
| **Analysis** | Human investigation | Automated log/metric analysis |
| **Remediation** | Manual code changes | Automated PR creation |
| **Review** | Code review | Code review (same) |
| **Deployment** | Manual or CI/CD | CI/CD (same) |
| **Availability** | Business hours | 24/7 |
| **Response Time** | Minutes to hours | Seconds to minutes |
| **Scalability** | Limited by team size | Unlimited (scales with targets) |

**Key Insight:** Leviathan augments human SREs, not replaces them. Humans still review and approve changes, but Leviathan handles detection, analysis, and PR creation.

---

## References

- [30_LEVIATHAN_ROADMAP.md](30_LEVIATHAN_ROADMAP.md) - Strategic roadmap
- [33_OBSERVABILITY_AND_OPERATOR_EXPERIENCE.md](33_OBSERVABILITY_AND_OPERATOR_EXPERIENCE.md) - Observability
- [32_MULTI_TARGET_ARCHITECTURE.md](32_MULTI_TARGET_ARCHITECTURE.md) - Multi-target design
- [00_CANONICAL_OVERVIEW.md](00_CANONICAL_OVERVIEW.md) - System overview

---

**Document Status:** Vision document, updated as SRE capabilities evolve.
