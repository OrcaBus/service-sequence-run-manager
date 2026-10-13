import { App, Stack } from 'aws-cdk-lib';
import { AwsSolutionsChecks } from 'cdk-nag';

/**
 * An App for cdk-nag tests that skips asset bundling, so the Python layer and functions
 * are not built in Docker: the checks only inspect the CloudFormation resources.
 */
export function newNagTestApp(): App {
  return new App({ context: { 'aws:cdk:bundling-stacks': [] } });
}

/**
 * A cdk-nag rule accepted for the tested stack, either stack-wide or only for the
 * construct at `path` (the v3 replacement for a v2 `NagSuppressions` entry).
 */
export interface AcceptedNagRule {
  id: string;
  reason: string;
  path?: string;
}

/**
 * The AwsSolutions findings of `severity` in `stack` that no accepted rule covers,
 * formatted as `<rule> at <construct path>`.
 *
 * cdk-nag v3 reports through `validateScope` rather than v2's synthesis annotations.
 * It walks the whole construct tree, so findings in nested stage stacks (e.g. those a
 * pipeline deploys) are skipped here, as `Annotations.fromStack` did in v2; those stacks
 * are tested on their own. Finding-level rule names such as `AwsSolutions-IAM5[Resource::*]`
 * match an accepted rule by their base id.
 */
export function unacceptedNagFindings(
  stack: Stack,
  accepted: AcceptedNagRule[],
  severity: 'error' | 'warning'
): string[] {
  const report = new AwsSolutionsChecks().validateScope(stack);
  const constructsByPath = new Map(stack.node.findAll().map((c) => [c.node.path, c]));
  const findings: string[] = [];

  for (const violation of report.violations) {
    if (violation.severity !== severity) {
      continue;
    }
    const ruleId = violation.ruleName.replace(/\[.*\]$/, '');
    for (const resource of violation.violatingResources) {
      const path = resource.constructPath ?? resource.resourceLogicalId ?? '<unknown>';
      const construct = constructsByPath.get(path);
      if (construct && Stack.of(construct) !== stack) {
        continue;
      }
      const isAccepted = accepted.some(
        (rule) => rule.id === ruleId && (rule.path === undefined || rule.path === path)
      );
      if (!isAccepted) {
        findings.push(`${violation.ruleName} at ${path}`);
      }
    }
  }
  return findings;
}
