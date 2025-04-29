import { getDefaultApiGatewayConfiguration } from '@orcabus/platform-cdk-constructs/api-gateway';
import { StageName } from '@orcabus/platform-cdk-constructs/utils';
import { VpcLookupOptions } from 'aws-cdk-lib/aws-ec2';
import { SequenceRunManagerStackProps } from './stack';

export const getSequenceRunManagerStackProps = (stage: StageName): SequenceRunManagerStackProps => {
  // upstream infra: vpc
  const vpcName = 'main-vpc';
  const vpcStackName = 'networking';
  const vpcProps: VpcLookupOptions = {
    vpcName: vpcName,
    tags: {
      Stack: vpcStackName,
    },
  };

  const computeSecurityGroupName = 'OrcaBusSharedComputeSecurityGroup';
  const eventBusName = 'OrcaBusMain';
  const basespaceAccessTokenSecretName = '/manual/BaseSpaceAccessTokenSecret'; // pragma: allowlist secret

  // slackTopicNameDict and orcabusUIBaseUrlDict are used to map the stage to the correct slack topic and orcabus UI base URL
  const slackTopicNameDict: Record<StageName, string> = {
    BETA: 'AwsChatBotTopic-alerts', // 'alerts-dev' channel binding topic
    GAMMA: 'AwsChatBotTopic-alerts', // 'alerts-stg' channel binding topic
    PROD: 'AwsChatBotTopic', // 'biobots' channel binding topic -- https://github.com/umccr/orcabus/issues/875
  };

  const orcabusUIBaseUrlDict: Record<StageName, string> = {
    BETA: 'https://orcaui.dev.umccr.org',
    GAMMA: 'https://orcaui.stg.umccr.org',
    PROD: 'https://orcaui.umccr.org',
  };

  return {
    vpcProps,
    lambdaSecurityGroupName: computeSecurityGroupName,
    mainBusName: eventBusName,
    apiGatewayCognitoProps: {
      ...getDefaultApiGatewayConfiguration(stage),
      apiName: 'SequenceRunManager',
      customDomainNamePrefix: 'sequence-dev-deploy',
    },
    bsshTokenSecretName: basespaceAccessTokenSecretName,
    slackTopicName: slackTopicNameDict[stage],
    orcabusUIBaseUrl: orcabusUIBaseUrlDict[stage],
  };
};
