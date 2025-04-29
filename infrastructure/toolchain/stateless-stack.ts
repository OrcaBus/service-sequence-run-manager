import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { DeploymentStackPipeline } from '@orcabus/platform-cdk-constructs/deployment-stack-pipeline';
import { SequenceRunManagerStack } from '../stage/stack';
import { getSequenceRunManagerStackProps } from '../stage/config';

export class StatelessStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    new DeploymentStackPipeline(this, 'DeploymentPipeline', {
      githubBranch: 'main',
      githubRepo: 'service-sequence-run-manager',
      stack: SequenceRunManagerStack,
      stackName: 'SequenceRunManagerStack',
      stackConfig: {
        beta: getSequenceRunManagerStackProps('BETA'),
        gamma: getSequenceRunManagerStackProps('GAMMA'),
        prod: getSequenceRunManagerStackProps('PROD'),
      },
      pipelineName: 'OrcaBus-StatelessSequnceRunManager',
      cdkSynthCmd: ['pnpm install --frozen-lockfile --ignore-scripts', 'pnpm cdk synth'],
    });
  }
}
