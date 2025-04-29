import { App, Aspects, Stack } from 'aws-cdk-lib';
import { Annotations, Match } from 'aws-cdk-lib/assertions';
import { SynthesisMessage } from 'aws-cdk-lib/cx-api';
import { AwsSolutionsChecks, NagSuppressions } from 'cdk-nag';
import { SequenceRunManagerStack } from '../infrastructure/stage/stack';
import { getSequenceRunManagerStackProps } from '../infrastructure/stage/config';

function synthesisMessageToString(sm: SynthesisMessage): string {
  return `${sm.entry.data} [${sm.id}]`;
}

describe('cdk-nag-stateless-toolchain-stack', () => {
  const app = new App({});

  // You should configure all stack (sateless, stateful) to be tested
  const deployStack = new SequenceRunManagerStack(app, 'SequenceRunManagerStack', {
    // Pick the prod environment to test as it is the most strict
    // ...getStackProps('PROD'),
    ...getSequenceRunManagerStackProps('PROD'),
    env: {
      account: '123456789',
      region: 'ap-southeast-2',
    },
  });

  Aspects.of(deployStack).add(new AwsSolutionsChecks());
  applyNagSuppression(deployStack);

  test(`cdk-nag AwsSolutions Pack errors`, () => {
    const errors = Annotations.fromStack(deployStack)
      .findError('*', Match.stringLikeRegexp('AwsSolutions-.*'))
      .map(synthesisMessageToString);
    expect(errors).toHaveLength(0);
  });

  test(`cdk-nag AwsSolutions Pack warnings`, () => {
    const warnings = Annotations.fromStack(deployStack)
      .findWarning('*', Match.stringLikeRegexp('AwsSolutions-.*'))
      .map(synthesisMessageToString);
    expect(warnings).toHaveLength(0);
  });
});

/**
 * apply nag suppression
 * @param stack
 */
function applyNagSuppression(stack: Stack) {
  NagSuppressions.addStackSuppressions(
    stack,
    [{ id: 'AwsSolutions-S10', reason: 'not require requests to use SSL' }],
    true
  );

  // FIXME one day we should remove this `AwsSolutions-IAM4` suppression and tackle any use of AWS managed policies
  //  in all our stacks. See https://github.com/umccr/orcabus/issues/174
  NagSuppressions.addStackSuppressions(
    stack,
    [{ id: 'AwsSolutions-IAM4', reason: 'allow to use AWS managed policy' }],
    true
  );

  NagSuppressions.addStackSuppressions(
    stack,
    [
      {
        id: 'AwsSolutions-APIG1',
        reason: 'See https://github.com/aws/aws-cdk/issues/11100',
      },
    ],
    true
  );

  NagSuppressions.addStackSuppressions(
    stack,
    [
      {
        id: 'AwsSolutions-APIG4',
        reason: 'We have the default Cognito UserPool authorizer',
      },
    ],
    true
  );

  // NOTE
  // This `AwsSolutions-L1` is tricky. Typically, it is okay to have one version less of the latest runtime
  // version. Not every dependency (including transitive packages) aren't upto speed with latest runtime.
  NagSuppressions.addStackSuppressions(
    stack,
    [
      {
        id: 'AwsSolutions-L1',
        reason:
          'Use the latest available runtime for the targeted language to avoid technical debt. ' +
          'Runtimes specific to a language or framework version are deprecated when the version ' +
          'reaches end of life. This rule only applies to non-container Lambda functions.',
      },
    ],
    true
  );
}
