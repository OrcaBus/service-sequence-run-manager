import { StatelessStack } from '../infrastructure/toolchain/stateless-stack';
import { AcceptedNagRule, newNagTestApp, unacceptedNagFindings } from './utils';

const ACCEPTED_RULES: AcceptedNagRule[] = [
  { id: 'AwsSolutions-IAM4', reason: 'Allow CDK Pipeline' },
  { id: 'AwsSolutions-IAM5', reason: 'Allow CDK Pipeline' },
  { id: 'AwsSolutions-S1', reason: 'Allow CDK Pipeline' },
  { id: 'AwsSolutions-KMS5', reason: 'Allow CDK Pipeline' },
  { id: 'AwsSolutions-CB3', reason: 'Allow CDK Pipeline' },
];

describe('cdk-nag-stateless-toolchain-stack', () => {
  const app = newNagTestApp();

  const statelessStack = new StatelessStack(app, 'StatelessStack', {
    env: {
      account: '123456789',
      region: 'ap-southeast-2',
    },
  });

  test(`cdk-nag AwsSolutions Pack errors`, () => {
    expect(unacceptedNagFindings(statelessStack, ACCEPTED_RULES, 'error')).toHaveLength(0);
  });

  test(`cdk-nag AwsSolutions Pack warnings`, () => {
    expect(unacceptedNagFindings(statelessStack, ACCEPTED_RULES, 'warning')).toHaveLength(0);
  });
});
