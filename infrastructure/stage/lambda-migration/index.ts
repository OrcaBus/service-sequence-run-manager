import { Construct } from 'constructs';
import { Duration } from 'aws-cdk-lib';
import { InvocationType, Trigger } from 'aws-cdk-lib/triggers';
import {
  ChainDefinitionBody,
  IntegrationPattern,
  Pass,
  StateMachine,
  Succeed,
  TaskInput,
} from 'aws-cdk-lib/aws-stepfunctions';
import {
  LambdaInvocationType,
  LambdaInvoke,
  StepFunctionsStartExecution,
} from 'aws-cdk-lib/aws-stepfunctions-tasks';
import {
  Architecture,
  DockerImageCode,
  DockerImageFunction,
  IFunction,
} from 'aws-cdk-lib/aws-lambda';
import path from 'path';

export class AutoTriggerBackupMigration extends Construct {
  /**
   * This construct orchestrates a database backup (pg-dd) of the sequence_run manager before running the migration lambda.
   * It works by chaining Step Functions and Lambda invocations to ensure backup occurs prior to migration.
   * Note: This implementation is a workaround, as Lambda must wait for other Lambda/StepFunction executions.
   * Consider refactoring for improved orchestration and maintainability in the future.
   */
  constructor(scope: Construct, id: string, migrationLambda: IFunction) {
    super(scope, id);

    // To invoke the migration lambda
    const lambdaMigrationStep = new LambdaInvoke(this, 'MigrationLambdaInvoke', {
      lambdaFunction: migrationLambda,
      integrationPattern: IntegrationPattern.REQUEST_RESPONSE,
      invocationType: LambdaInvocationType.REQUEST_RESPONSE,
      payload: TaskInput.fromObject({}),
    });

    // Execute the backup step (pg-dd)
    const backupStateMachine = StateMachine.fromStateMachineName(
      this,
      'BackupStateMachine',
      'orcabus-pg-dd'
    );
    const backupPgDDStep = new StepFunctionsStartExecution(this, 'ExecuteBackup', {
      stateMachine: backupStateMachine,
      integrationPattern: IntegrationPattern.RUN_JOB,
      input: TaskInput.fromObject({
        commands: ['upload', '--dump-db', '--database', 'sequence_run_manager'],
      }),
    });

    // Create state machine to orchestrate the backup and migration steps
    const startState = new Pass(this, 'StartState');
    const finish = new Succeed(this, 'SuccessState');

    const backupMigrationStep = new StateMachine(this, 'backupMigrationStep', {
      stateMachineName: 'orcabus-sequence-run-manager-migration',
      definitionBody: ChainDefinitionBody.fromChainable(
        startState.next(backupPgDDStep).next(lambdaMigrationStep).next(finish)
      ),
    });

    backupStateMachine.grantStartExecution(backupMigrationStep);
    backupStateMachine.grantRead(backupMigrationStep);

    // Trigger lambda to start the backup-migration step function
    const triggerLambda = new DockerImageFunction(this, 'TriggerStepLambda', {
      architecture: Architecture.ARM_64,
      code: DockerImageCode.fromImageAsset(path.join(__dirname, '../../../'), {
        file: 'infrastructure/stage/lambda-migration/trigger-handler/Dockerfile',
      }),
      timeout: Duration.minutes(10),
      memorySize: 128,
      environment: {
        STATE_MACHINE_ARN: backupMigrationStep.stateMachineArn,
      },
    });

    backupMigrationStep.grantStartExecution(triggerLambda);
    backupMigrationStep.grantRead(triggerLambda);

    new Trigger(this, 'ExecuteBackupStepLambdaTrigger', {
      handler: triggerLambda,
      timeout: Duration.minutes(10),
      invocationType: InvocationType.REQUEST_RESPONSE,
    });
  }
}
