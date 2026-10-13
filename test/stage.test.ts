import { SequenceRunManagerStack } from '../infrastructure/stage/stack';
import { getSequenceRunManagerStackProps } from '../infrastructure/stage/config';
import { AcceptedNagRule, newNagTestApp, unacceptedNagFindings } from './utils';

const BACKUP_MIGRATION_STEP_PATH =
  'SequenceRunManagerStack/AutoTriggerBackupMigration/backupMigrationStep/Resource';

const ACCEPTED_RULES: AcceptedNagRule[] = [
  { id: 'AwsSolutions-S10', reason: 'not require requests to use SSL' },

  // FIXME one day we should remove this `AwsSolutions-IAM4` suppression and tackle any use of AWS managed policies
  //  in all our stacks. See https://github.com/umccr/orcabus/issues/174
  { id: 'AwsSolutions-IAM4', reason: 'allow to use AWS managed policy' },

  { id: 'AwsSolutions-APIG1', reason: 'See https://github.com/aws/aws-cdk/issues/11100' },
  { id: 'AwsSolutions-APIG4', reason: 'We have the default Cognito UserPool authorizer' },

  // NOTE
  // This `AwsSolutions-L1` is tricky. Typically, it is okay to have one version less of the latest runtime
  // version. Not every dependency (including transitive packages) aren't upto speed with latest runtime.
  {
    id: 'AwsSolutions-L1',
    reason:
      'Use the latest available runtime for the targeted language to avoid technical debt. ' +
      'Runtimes specific to a language or framework version are deprecated when the version ' +
      'reaches end of life. This rule only applies to non-container Lambda functions.',
  },

  {
    id: 'AwsSolutions-IAM5',
    reason:
      '* is required to access the temporary linking data files by the enrichment lambda function.',
    path: 'SequenceRunManagerStack/LambdaRole/DefaultPolicy/Resource',
  },
  { id: 'AwsSolutions-IAM5', reason: 'Allow wildcard permissions based.' },

  {
    id: 'AwsSolutions-SF1',
    reason: 'Disable cloudwatch logs for simple Step Functions.',
    path: BACKUP_MIGRATION_STEP_PATH,
  },
  { id: 'AwsSolutions-SF2', reason: 'Disable X-Ray for now.', path: BACKUP_MIGRATION_STEP_PATH },
];

describe('cdk-nag-stateless-toolchain-stack', () => {
  const app = newNagTestApp();

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

  test(`cdk-nag AwsSolutions Pack errors`, () => {
    expect(unacceptedNagFindings(deployStack, ACCEPTED_RULES, 'error')).toHaveLength(0);
  });

  test(`cdk-nag AwsSolutions Pack warnings`, () => {
    expect(unacceptedNagFindings(deployStack, ACCEPTED_RULES, 'warning')).toHaveLength(0);
  });
});
