import { EVENT_SCHEMA_REGISTRY_NAME } from '@orcabus/platform-cdk-constructs/shared-config/event-bridge';
import { CfnSchema } from 'aws-cdk-lib/aws-eventschemas';
import { Construct } from 'constructs';
import { readFileSync } from 'fs';
import path from 'path';

export interface SchemaProps {
  schemaName: string;
  schemaDescription: string;
  schemaLocation: string;
}

export class SequenceRunManagerSchemaRegistry extends Construct {
  private readonly SCHEMA_TYPE = 'JSONSchemaDraft4';

  constructor(scope: Construct, id: string) {
    super(scope, id);

    // Publish schema into the registry
    getSchemas().forEach((s) => {
      new CfnSchema(this, s.schemaName, {
        content: readFileSync(s.schemaLocation, 'utf-8'),
        type: this.SCHEMA_TYPE,
        registryName: EVENT_SCHEMA_REGISTRY_NAME,
        description: s.schemaDescription,
        schemaName: s.schemaName,
      });
    });
  }
}

export const getSchemas = (): Array<SchemaProps> => {
  const docBase: string = '../../docs/events';
  const SCHEMA_REGISTRY_NAME = 'orcabus.sequencerunmanager';

  return [
    {
      schemaName: SCHEMA_REGISTRY_NAME + '@SequenceRunStateChange',
      schemaDescription: 'State change event for sequence run by SequenceRunManager',
      schemaLocation: path.join(
        __dirname,
        docBase + '/SequenceRunStateChange/SequenceRunStateChange.schema.json'
      ),
    },
    {
      schemaName: SCHEMA_REGISTRY_NAME + '@SequenceRunSampleSheetChange',
      schemaDescription: 'Sample sheet change event for sequence run by SequenceRunManager',
      schemaLocation: path.join(
        __dirname,
        docBase + '/SequenceRunSampleSheetChange/SequenceRunSampleSheetChange.schema.json'
      ),
    },
    {
      schemaName: SCHEMA_REGISTRY_NAME + '@SequenceRunLibraryLinkingChange',
      schemaDescription: 'Library linking change event for sequence run by SequenceRunManager',
      schemaLocation: path.join(
        __dirname,
        docBase + '/SequenceRunLibraryLinkingChange/SequenceRunLibraryLinkingChange.schema.json'
      ),
    },
  ];
};
