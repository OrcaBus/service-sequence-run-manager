import { getDefaultApiGatewayConfiguration } from '@orcabus/platform-cdk-constructs/api-gateway';
import { StageName } from '@orcabus/platform-cdk-constructs/shared-config/accounts';
import {
  VPC_LOOKUP_PROPS,
  SHARED_SECURITY_GROUP_NAME,
} from '@orcabus/platform-cdk-constructs/shared-config/networking';
import { EVENT_BUS_NAME } from '@orcabus/platform-cdk-constructs/shared-config/event-bridge';
import { SequenceRunManagerStackProps } from './stack';

export const getSequenceRunManagerStackProps = (stage: StageName): SequenceRunManagerStackProps => {
  // config bssh token secret name
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

  const sequenceRunManagerBaseApiUrlDict: Record<StageName, string> = {
    BETA: 'https://sequence.dev.umccr.org',
    GAMMA: 'https://sequence.stg.umccr.org',
    PROD: 'https://sequence.prod.umccr.org',
  };

  return {
    vpcProps: VPC_LOOKUP_PROPS,
    lambdaSecurityGroupName: SHARED_SECURITY_GROUP_NAME,
    mainBusName: EVENT_BUS_NAME,
    apiGatewayCognitoProps: {
      ...getDefaultApiGatewayConfiguration(stage),
      apiName: 'SequenceRunManager',
      customDomainNamePrefix: 'sequence',
    },
    bsshTokenSecretName: basespaceAccessTokenSecretName,
    slackTopicName: slackTopicNameDict[stage],
    orcabusUIBaseUrl: orcabusUIBaseUrlDict[stage],
    sequenceRunManagerBaseApiUrl: sequenceRunManagerBaseApiUrlDict[stage],
  };
};
