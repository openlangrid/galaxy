import unittest

from galaxy import model
from galaxy.workflow.run import WorkflowProgress

from .workflow_support import TestApp, yaml_to_model

TEST_WORKFLOW_YAML = """
steps:
  - type: "data_input"
    tool_inputs: {"name": "input1"}
  - type: "data_input"
    tool_inputs: {"name": "input2"}
  - type: "tool"
    tool_id: "cat1"
    input_connections:
    -  input_name: "input1"
       "@output_step": 0
       output_name: "output"
  - type: "tool"
    tool_id: "cat1"
    input_connections:
    -  input_name: "input1"
       "@output_step": 0
       output_name: "output"
  - type: "tool"
    tool_id: "cat1"
    input_connections:
    -  input_name: "input1"
       "@output_step": 2
       output_name: "out_file1"
"""

UNSCHEDULED_STEP = object()


class WorkflowProgressTestCase( unittest.TestCase ):

    def setUp(self):
        self.app = TestApp()
        self.inputs_by_step_id = {}
        self.invocation = model.WorkflowInvocation()
        self.progress = {}

    def _setup_workflow(self, workflow_yaml):
        workflow = yaml_to_model(TEST_WORKFLOW_YAML)
        self.invocation.workflow = workflow

    def _new_workflow_progress( self ):
        return WorkflowProgress(
            self.invocation, self.inputs_by_step_id, MockModuleInjector(self.progress)
        )

    def _set_previous_progress(self, outputs_dict):
        for step_id, step_value in outputs_dict.iteritems():
            if step_value is not UNSCHEDULED_STEP:
                self.progress[step_id] = step_value

                workflow_invocation_step = model.WorkflowInvocationStep()
                workflow_invocation_step.workflow_step_id = step_id
                self.invocation.steps.append(workflow_invocation_step)

            workflow_invocation_step_state = model.WorkflowRequestStepState()
            workflow_invocation_step_state.workflow_step_id = step_id
            workflow_invocation_step_state.value = True
            self.invocation.step_states.append(workflow_invocation_step_state)

    def _step(self, index):
        return self.invocation.workflow.steps[index]

    def test_connect_data_input( self ):
        self._setup_workflow(TEST_WORKFLOW_YAML)
        hda = model.HistoryDatasetAssociation()

        self.inputs_by_step_id = {100: hda}
        progress = self._new_workflow_progress()
        progress.set_outputs_for_input( self._step(0) )

        conn = model.WorkflowStepConnection()
        conn.output_name = "output"
        conn.output_step = self._step(0)
        assert progress.replacement_for_connection(conn) is hda

    def test_replacement_for_tool_input( self ):
        self._setup_workflow(TEST_WORKFLOW_YAML)
        hda = model.HistoryDatasetAssociation()

        self.inputs_by_step_id = {100: hda}
        progress = self._new_workflow_progress()
        progress.set_outputs_for_input( self._step(0) )

        replacement = progress.replacement_for_tool_input(self._step(2), MockInput(), "input1")
        assert replacement is hda

    def test_connect_tool_output( self ):
        self._setup_workflow(TEST_WORKFLOW_YAML)
        hda = model.HistoryDatasetAssociation()

        progress = self._new_workflow_progress()
        progress.set_step_outputs( self._step(2), {"out1": hda} )

        conn = model.WorkflowStepConnection()
        conn.output_name = "out1"
        conn.output_step = self._step(2)
        assert progress.replacement_for_connection(conn) is hda

    def test_remaining_steps_with_progress(self):
        self._setup_workflow(TEST_WORKFLOW_YAML)
        hda3 = model.HistoryDatasetAssociation()
        self._set_previous_progress({
            100: {"output": model.HistoryDatasetAssociation()},
            101: {"output": model.HistoryDatasetAssociation()},
            102: {"out_file1": hda3},
            103: {"out_file1": model.HistoryDatasetAssociation()},
            104: UNSCHEDULED_STEP,
        })
        progress = self._new_workflow_progress()
        steps = progress.remaining_steps()
        assert len(steps) == 1
        assert steps[0] is self.invocation.workflow.steps[4]

        replacement = progress.replacement_for_tool_input(self._step(4), MockInput(), "input1")
        assert replacement is hda3

    # TODO: Replace multiple true HDA with HDCA
    # TODO: Test explicit delay
    # TODO: Test cancel on collection invalid
    # TODO: Test delay on collection waiting for population


class MockInput(object):

    def __init__(self, multiple=False):
        self.multiple = multiple


class MockModuleInjector(object):

    def __init__(self, progress):
        self.progress = progress

    def inject(self, step):
        step.module = MockModule(self.progress)


class MockModule(object):

    def __init__(self, progress):
        self.progress = progress

    def recover_runtime_state(self, runtime_state):
        return True

    def recover_mapping(self, step, step_invocations, progress):
        step_id = step.id
        if step_id in self.progress:
            progress.set_step_outputs(step, self.progress[step_id])
