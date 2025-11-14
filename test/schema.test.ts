import * as cdk from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { SequenceRunManagerSchemaRegistry } from '../infrastructure/stage/event-schema';
let stack: cdk.Stack;

beforeEach(() => {
  stack = new cdk.Stack();
});

test('Test orcabus.sequencerunmanager SequenceRunManagerSchemaRegistry Creation', () => {
  // pnpm test --- test/schema.test.ts

  new SequenceRunManagerSchemaRegistry(stack, 'TestSequenceRunManagerSchemaRegistry');
  const template = Template.fromStack(stack);

  console.log(template.toJSON());

  template.hasResourceProperties('AWS::EventSchemas::Schema', {
    SchemaName: 'orcabus.sequencerunmanager@SequenceRunStateChange',
  });

  template.hasResourceProperties('AWS::EventSchemas::Schema', {
    SchemaName: 'orcabus.sequencerunmanager@SequenceRunSampleSheetChange',
  });

  template.hasResourceProperties('AWS::EventSchemas::Schema', {
    SchemaName: 'orcabus.sequencerunmanager@SequenceRunLibraryLinkingChange',
  });
});
