import { Construct } from 'constructs';
import { aws_eventschemas } from 'aws-cdk-lib';
import { readFileSync } from 'fs';
import path from 'path';

export interface SchemaProps {
  schemaName: string;
  schemaDescription: string;
  schemaLocation: string;
}

export class SequenceRunManagerSchemaRegistry extends Construct {
  private readonly SCHEMA_REGISTRY_NAME = 'orcabus.sequencerunmanager';
  private readonly SCHEMA_TYPE = 'JSONSchemaDraft4';

  constructor(scope: Construct, id: string) {
    super(scope, id);

    // Create EventBridge schema registry
    const registry = new aws_eventschemas.CfnRegistry(this, this.SCHEMA_REGISTRY_NAME, {
      registryName: this.SCHEMA_REGISTRY_NAME,
      description: 'Schema Registry for ' + this.SCHEMA_REGISTRY_NAME,
    });

    // Publish schema into the registry
    getSchemas().forEach((s) => {
      const schema = new aws_eventschemas.CfnSchema(this, s.schemaName, {
        content: readFileSync(s.schemaLocation, 'utf-8'),
        type: this.SCHEMA_TYPE,
        registryName: registry.registryName as string,
        description: s.schemaDescription,
        schemaName: s.schemaName,
      });

      // Make Schema component depends on the Registry component
      // Essentially, it forms the deployment dependency at CloudFormation
      schema.addDependency(registry);
    });
  }
}

export const getSchemas = (): Array<SchemaProps> => {
  const docBase: string = '../../docs/events';

  return [
    {
      schemaName: 'orcabus.sequencerunmanager@SequenceRunStateChange',
      schemaDescription: 'State change event for sequence run by SequenceRunManager',
      schemaLocation: path.join(
        __dirname,
        docBase + '/SequenceRunStateChange/SequenceRunStateChange.schema.json'
      ),
    },
    {
      schemaName: 'orcabus.sequencerunmanager@SequenceRunSampleSheetChange',
      schemaDescription: 'Sample sheet change event for sequence run by SequenceRunManager',
      schemaLocation: path.join(
        __dirname,
        docBase + '/SequenceRunSampleSheetChange/SequenceRunSampleSheetChange.schema.json'
      ),
    },
    {
      schemaName: 'orcabus.sequencerunmanager@SequenceRunLibraryLinkingChange',
      schemaDescription: 'Library linking change event for sequence run by SequenceRunManager',
      schemaLocation: path.join(
        __dirname,
        docBase + '/SequenceRunLibraryLinkingChange/SequenceRunLibraryLinkingChange.schema.json'
      ),
    },
  ];
};
