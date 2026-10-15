"""Scripted worker outputs through the recipe's loop wiring and real Bash guards.

No provider/delegate is contacted. These tests exercise routing, durable receipts,
failure diagnostics, and resume with subprocesses, not a live cross-family workflow.
The small condition adapter supports this recipe's equality/and/or expressions;
installed-engine verification is intentionally separate from this stdlib suite.
"""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from test_user_request_contract import (
    RECIPE, ROOT, render_bash_step, step_field, step_section, top_level_steps,
)


def resolve(reference, context):
    value = context
    for part in reference.split('.'):
        value = value[part]
    return value


def evaluate(expression, context):
    def compare(atom):
        match = re.fullmatch(r"\s*\{\{([\w.]+)\}\}\s*(==|!=)\s*'([^']*)'\s*", atom)
        if match is None:
            raise AssertionError(f'unsupported test expression: {atom}')
        equal = resolve(match[1], context) == match[3]
        return equal if match[2] == '==' else not equal
    # Evaluate all atoms, so missing initial variables fail even in unused arms.
    groups = [[compare(atom) for atom in group.split(' and ')]
              for group in expression.split(' or ')]
    return any(all(group) for group in groups)


# A scripted worker persists its receipt before returning, as required by the
# actual prompt. Counts/verdicts are explicit fixture inputs, not computed by a
# second implementation of the review classifier.
WORKER = '''
import json, os
from pathlib import Path
fixture = json.loads(Path(os.environ['FIXTURE']).read_text())
logs = Path(os.environ['LOGS'])
with (logs / 'calls.jsonl').open('a') as calls:
    calls.write(json.dumps(fixture['events']) + '\\n')
for target, receipt in fixture['receipts'].items():
    (logs / ('fresheyes-' + target + '-result.json')).write_text(json.dumps(receipt))
print(json.dumps(fixture['receipts'][os.environ['TARGET']]))
'''
PASS = '## Issues Found\nNone.\n\n**INDEPENDENT CODE REVIEW PASSED**'
FAIL = '## Issues Found\n- **major** `app.py:1` - Wrong return value.\n\nINDEPENDENT CODE REVIEW FAILED'
MALFORMED = 'At app.py:1 the return value is wrong; add the missing boundary case.'


class ReviewExecutionFailureTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.logs = self.directory / 'logs'
        self.logs.mkdir()
        self.repo = self.directory / 'worktree'
        self.repo.mkdir()
        for args in (
            ['init', '-q'],
            ['-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
             'commit', '--allow-empty', '-qm', 'fixture'],
        ):
            subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True)
        self.context = {
            key: value for key, value in re.findall(
                r'^  ((?:plan|delta)_(?:passed|execution_blocked)): "([^"]+)"',
                RECIPE, re.MULTILINE,
            )
        }
        self.events = []
        self.serial = 0

    def receipt(self, target, verdict='NOT_RUN', rounds=0, *, blocked='', report=None):
        self.serial += 1
        report_path = ''
        if rounds:
            path = self.logs / f'{target}-report-{self.serial}.md'
            path.write_text(report if report is not None else {'PASSED': PASS, 'FAILED': FAIL, 'NO_MARKER': MALFORMED}[verdict])
            report_path = str(path)
        evidence = []
        if blocked:
            attempt = self.logs / f'{target}-attempt-{self.serial}.txt'
            attempt.write_text('native delegate configured provider/model: ' + blocked)
            evidence.append(str(attempt))
        return {
            'passed': 'true' if verdict == 'PASSED' and not blocked else 'false',
            'execution_blocked': 'true' if blocked else 'false',
            'verdict': verdict, 'rounds_completed': rounds, 'blocking_count': 0,
            'blocked_target': target if blocked else '', 'blocker_reason': blocked,
            'evidence_paths': evidence, 'report_path': report_path,
            'summary': blocked or 'scripted substantive review',
        }

    def guard(self, target, phase):
        step = f'fresheyes-{target}-{"resume" if phase == "pre" else "halt"}-guard'
        values = {
            'workspace.logs_dir': str(self.logs), 'workspace.worktree_path': str(self.repo),
            f'fresheyes_{target}_result': json.dumps(self.context.get(f'fresheyes_{target}_result', {})),
            f'{target}_execution_blocked': self.context[f'{target}_execution_blocked'],
            f'{target}_passed': self.context[f'{target}_passed'],
        }
        command, env = render_bash_step(step_section(step), values)
        return subprocess.run(['bash', '-c', command], env=env, cwd=self.directory,
                              text=True, capture_output=True, timeout=10)

    def loop(self, target, fixtures):
        pre = self.guard(target, 'pre')
        if pre.returncode:
            return pre
        section = step_section(f'fresheyes-{target}')
        condition = step_field(section, 'while_condition')
        stop = step_field(section, 'break_when')
        output = step_field(section, 'output')
        updates = re.search(r'    update_context:\n((?:      .*\n)+)', section)[1]
        cap = int(step_field(section, 'max_while_iterations'))
        for iteration in range(cap):
            if not evaluate(condition, self.context):
                break
            fixture = fixtures[iteration]  # Unexpected extra calls fail the test.
            path = self.directory / 'scripted-output.json'
            path.write_text(json.dumps(fixture))
            result = subprocess.run(
                [sys.executable, '-c', WORKER],
                env={**os.environ, 'FIXTURE': str(path), 'LOGS': str(self.logs), 'TARGET': target},
                text=True, capture_output=True, check=True, timeout=10,
            )
            self.events.extend(fixture['events'])
            self.context[output] = json.loads(result.stdout)
            for key, reference in re.findall(r'      (\w+): "\{\{([\w.]+)\}\}"', updates):
                self.context[key] = resolve(reference, self.context)
            if evaluate(stop, self.context):
                break
        post = self.guard(target, 'post')
        if post.returncode == 0:
            self.events.append('execute-plan' if target == 'plan' else 'final-gate')
        return post

    @staticmethod
    def fixture(target, receipt, *, events=None, focused=None):
        receipts = {target: receipt}
        if focused is not None:
            receipts['focused'] = focused
        return {'events': events or [target + '-delegate'], 'receipts': receipts}

    def diagnostic(self):
        text = (self.logs / 'review-execution-failure.md').read_text()
        self.assertIn('WORKFLOW STOPPED', text)
        self.assertNotIn('## Outcome Block', text)
        return text

    def test_first_unavailable_attempt_stops_after_one_call_and_reports_zero(self):
        for target in ('plan', 'delta'):
            with self.subTest(target=target):
                # Independent run for each loop.
                if target == 'delta':
                    self.setUp()
                receipt = self.receipt(target, blocked='delegate unavailable; supported routes exhausted')
                result = self.loop(target, [self.fixture(target, receipt)])
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertEqual([target + '-delegate'], self.events)
                self.assertEqual('true', self.context[target + '_execution_blocked'])
                self.assertIn(f'{target.title()} review: 0 completed; last verdict NOT_RUN.', self.diagnostic())

    def test_substantive_failure_then_unavailable_preserves_completed_round(self):
        first = self.receipt('plan', 'FAILED', 1)
        blocked = deepcopy(first)
        attempt = self.receipt('plan', blocked='review timeout')
        blocked.update({key: attempt[key] for key in ('execution_blocked', 'blocked_target', 'blocker_reason', 'evidence_paths')})
        result = self.loop('plan', [self.fixture('plan', first), self.fixture('plan', blocked)])
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertEqual(['plan-delegate', 'plan-delegate'], self.events)
        self.assertIn('Plan review: 1 completed; last verdict FAILED.', self.diagnostic())
        self.assertEqual(first['report_path'], self.context['fresheyes_plan_result']['report_path'])

    def test_focused_failure_returns_blocked_delta_and_skips_next_delta_and_gate(self):
        focused = self.receipt('focused', blocked='reviewer cannot perform meaningful review')
        delta = self.receipt('delta', 'FAILED', 1)
        delta.update({key: focused[key] for key in ('execution_blocked', 'blocked_target', 'blocker_reason', 'evidence_paths')})
        fixture = self.fixture('delta', delta, focused=focused,
                               events=['delta-delegate', 'delta-repair', 'focused-delegate'])
        (self.logs / 'execute-result.json').write_text(json.dumps({'tasks_completed': 2, 'total_tasks': 3}))
        result = self.loop('delta', [fixture])
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertEqual(fixture['events'], self.events)
        diagnostic = self.diagnostic()
        self.assertIn('Execution tasks: 2 of 3 completed.', diagnostic)
        self.assertIn('Delta review: 1 completed; last verdict FAILED.', diagnostic)
        self.assertIn('No full-suite gate was run by this guard', diagnostic)
        self.assertIn('focused review execution blocked', diagnostic)
        self.assertEqual(0, json.loads((self.logs / 'fresheyes-focused-result.json').read_text())['rounds_completed'])

    def test_malformed_substantive_report_remains_feedback_then_pass_stops(self):
        first = self.receipt('delta', 'NO_MARKER', 1, report=MALFORMED)
        passed = self.receipt('delta', 'PASSED', 2)
        result = self.loop('delta', [self.fixture('delta', first), self.fixture('delta', passed)])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(['delta-delegate', 'delta-delegate', 'final-gate'], self.events)
        self.assertEqual(2, self.context['fresheyes_delta_result']['rounds_completed'])
        self.assertFalse((self.logs / 'review-execution-blocker.json').exists())

    def test_valid_pass_stops_after_one_call(self):
        result = self.loop('plan', [self.fixture('plan', self.receipt('plan', 'PASSED', 1))])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(['plan-delegate', 'execute-plan'], self.events)

    def test_capped_substantive_plan_failure_continues_at_three(self):
        result = self.loop('plan', [self.fixture('plan', self.receipt('plan', 'FAILED', n)) for n in range(1, 4)])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(['plan-delegate'] * 3 + ['execute-plan'], self.events)
        self.assertEqual('false', self.context['plan_passed'])
        self.assertFalse((self.logs / 'recap.md').exists())

    def test_delta_cap_still_five_and_no_marker_is_not_pass(self):
        result = self.loop('delta', [self.fixture('delta', self.receipt('delta', 'NO_MARKER', n,
                           report='## Issues Found\n- **nit** `app.py:1` - Cosmetic only.')) for n in range(1, 6)])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(5, self.events.count('delta-delegate'))
        self.assertEqual('false', self.context['delta_passed'])

    def test_terminal_blocker_persists_on_resume_with_stale_flags(self):
        receipt = self.receipt('delta', blocked='supported routes exhausted')
        result = self.loop('delta', [self.fixture('delta', receipt)])
        self.assertEqual(1, result.returncode)
        evidence = (self.logs / 'review-execution-blocker.json').read_bytes()
        calls = (self.logs / 'calls.jsonl').read_bytes()
        for target in ('plan', 'delta'):
            self.context[target + '_execution_blocked'] = 'false'
            self.context[target + '_passed'] = 'false'
            result = self.loop(target, [])
            self.assertEqual(1, result.returncode, result.stderr)
        self.assertEqual(calls, (self.logs / 'calls.jsonl').read_bytes())
        self.assertEqual(evidence, (self.logs / 'review-execution-blocker.json').read_bytes())

    def test_receipt_alone_blocks_resume_before_global_marker_is_written(self):
        receipt = self.receipt('focused', 'NO_MARKER', 2, blocked='no report on third attempt')
        (self.logs / 'fresheyes-focused-result.json').write_text(json.dumps(receipt))
        result = self.loop('delta', [])
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertEqual([], self.events)
        self.assertTrue((self.logs / 'review-execution-blocker.json').exists())
        saved = json.loads((self.logs / 'fresheyes-focused-result.json').read_text())
        self.assertEqual(2, saved['rounds_completed'])
        self.assertEqual('NO_MARKER', saved['verdict'])

    def test_terminal_marker_alone_blocks_dispatch_and_retains_route_evidence(self):
        blocker = {
            'target': 'plan', 'reason': 'same-family refusal',
            'attempted_routes': ['configured native delegate rejected before dispatch'],
            'delegate_status': 'refused', 'evidence_paths': [],
        }
        path = self.logs / 'review-execution-blocker.json'
        path.write_text(json.dumps(blocker))
        before = path.read_bytes()
        result = self.loop('plan', [])
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertEqual([], self.events)
        self.assertFalse((self.logs / 'calls.jsonl').exists())
        self.assertEqual(before, path.read_bytes())
        self.assertIn(blocker['attempted_routes'][0], result.stdout)
        self.assertIn('Plan review: no completed-review receipt available; no count inferred.', self.diagnostic())
        self.assertIn('Execution task counts unavailable; no totals inferred.', self.diagnostic())

    def test_valid_pass_can_describe_fixed_failure_and_list_major_filename(self):
        report = (
            "## Files Examined\n- major.py\n"
            "## Issues Found\nNone.\n"
            "## Summary\nThe old code could not perform validation; the fix now handles it.\n"
            "INDEPENDENT CODE REVIEW PASSED"
        )
        receipt = self.receipt('plan', 'PASSED', 1, report=report)
        result = self.loop('plan', [self.fixture('plan', receipt)])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(['plan-delegate', 'execute-plan'], self.events)

    def test_valid_pass_accepts_quoted_markers_and_absent_severity_findings(self):
        reports = (
            '## Issues Found\nNone.\n## Summary\n'
            'The parser now handles the literal `INDEPENDENT CODE REVIEW FAILED`.\n'
            'INDEPENDENT CODE REVIEW PASSED',
            '## Issues Found\n- **Critical**: none.\n- **Major**: none.\n'
            '## Summary\nNo blocking issues remain.\nINDEPENDENT CODE REVIEW PASSED',
        )
        for report in reports:
            with self.subTest(report=report):
                self.setUp()
                receipt = self.receipt('plan', 'PASSED', 1, report=report)
                result = self.loop('plan', [self.fixture('plan', receipt)])
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(['plan-delegate', 'execute-plan'], self.events)
                self.assertFalse((self.logs / 'review-execution-blocker.json').exists())

    def test_execution_failure_preserves_existing_gate_and_recap_evidence(self):
        # A review outage must not rewrite evidence of verification that ran.
        previous_recap = self.logs / 'recap.md'
        previous_recap.write_text('Earlier factual recap; preserve it.\n')
        gate = self.repo / '.git' / 'sdd' / 'progress.md'
        gate.parent.mkdir()
        gate.write_text('## Baseline\nRecorded.\n## Gate\nresult: passed\n')
        execution = {'tasks_completed': 2, 'total_tasks': 3}
        (self.logs / 'execute-result.json').write_text(json.dumps(execution))
        originals = {path: path.read_bytes() for path in (previous_recap, gate)}
        receipt = self.receipt('delta', blocked='reviewer unavailable')
        result = self.loop('delta', [self.fixture('delta', receipt)])
        self.assertEqual(1, result.returncode, result.stderr)
        for path, expected in originals.items():
            self.assertEqual(expected, path.read_bytes())
        diagnostic = (self.logs / 'review-execution-failure.md').read_text()
        self.assertIn('Execution tasks: 2 of 3 completed.', diagnostic)
        self.assertIn('No full-suite gate was run by this guard', diagnostic)
        self.assertNotIn('## Outcome Block', diagnostic)
        self.assertIn('reviewer unavailable', result.stderr)

    def test_false_success_refusal_and_invalid_pass_fail_closed(self):
        reports = (
            '## Issues Found\nUnable to review.\nINDEPENDENT CODE REVIEW PASSED',
            '## Issues Found\nI could not perform a meaningful review.\nINDEPENDENT CODE REVIEW PASSED',
            '## Issues Found\n- **nit** `a:1` - Optional naming.',
            'INDEPENDENT CODE REVIEW PASSED',
            '## Issues Found\n- **major** `a:1` - Broken.\nINDEPENDENT CODE REVIEW PASSED',
            '## Issues Found\nINDEPENDENT CODE REVIEW FAILED\nINDEPENDENT CODE REVIEW PASSED',
        )
        for report in reports:
            with self.subTest(report=report):
                self.setUp()
                result = self.loop('plan', [self.fixture('plan', self.receipt('plan', 'PASSED', 1, report=report))])
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertNotIn('execute-plan', self.events)
                self.assertTrue((self.logs / 'review-execution-blocker.json').exists())

    def test_all_execution_failure_reasons_are_terminal_even_failed_marker(self):
        for reason in ('same-family refusal', 'delegate unavailable', 'reviewer unavailable',
                       'supported routes exhausted', 'no report', 'timeout',
                       'I cannot perform a meaningful review. INDEPENDENT CODE REVIEW FAILED'):
            with self.subTest(reason=reason):
                self.setUp()
                receipt = self.receipt('plan', blocked=reason)
                result = self.loop('plan', [self.fixture('plan', receipt)])
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertEqual(['plan-delegate'], self.events)
                self.assertIn('Plan review: 0 completed; last verdict NOT_RUN.', self.diagnostic())

    def test_guards_reject_missing_receipt_mismatch_and_false_success_flags(self):
        cases = ('missing', 'mismatch', 'blocked-pass', 'markerless-pass', 'count-verdict', 'flag-mismatch')
        for case in cases:
            with self.subTest(case=case):
                self.setUp()
                receipt = self.receipt('plan', 'NO_MARKER', 1)
                if case == 'blocked-pass':
                    receipt = self.receipt('plan', blocked='no report')
                    receipt['passed'] = 'true'
                elif case == 'markerless-pass':
                    receipt['passed'] = 'true'
                elif case == 'count-verdict':
                    receipt['rounds_completed'] = 0
                self.context['fresheyes_plan_result'] = receipt
                self.context['plan_passed'] = receipt['passed']
                self.context['plan_execution_blocked'] = receipt['execution_blocked']
                if case != 'missing':
                    saved = deepcopy(receipt)
                    if case == 'mismatch':
                        saved['summary'] = 'different output'
                    (self.logs / 'fresheyes-plan-result.json').write_text(json.dumps(saved))
                if case == 'flag-mismatch':
                    self.context['plan_execution_blocked'] = 'true'
                result = self.guard('plan', 'post')
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertTrue((self.logs / 'review-execution-blocker.json').exists())

    def test_guard_dynamic_channels_are_inert(self):
        self.logs = self.directory / 'logs $(touch INJECTED) `touch ALSO_INJECTED`\n"quoted"'
        self.logs.mkdir()
        reason = 'delegate unavailable $(touch REASON_INJECTED)'
        receipt = self.receipt('plan', blocked=reason)
        result = self.loop('plan', [self.fixture('plan', receipt)])
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertFalse([path for path in self.directory.rglob('*')
                          if path.name in {'INJECTED', 'ALSO_INJECTED', 'REASON_INJECTED'}])
        self.assertIn(reason, self.diagnostic())

    def test_initial_flags_contract_copies_and_guard_placement(self):
        self.assertEqual({'plan_passed': 'false', 'delta_passed': 'false',
                          'plan_execution_blocked': 'false', 'delta_execution_blocked': 'false'}, self.context)
        order = [name for name, _ in top_level_steps()]
        for target in ('plan', 'delta'):
            section = step_section(f'fresheyes-{target}')
            contracts = re.findall(r'Return ONLY a JSON object \(no prose, no fences\) with exactly:\n(      \{.*?\n      \})', section, re.S)
            self.assertEqual(2, len(contracts))
            self.assertEqual(json.loads(contracts[0]), json.loads(contracts[1]))
            self.assertEqual(set(self.receipt(target)), set(json.loads(contracts[0])))
            index = order.index(f'fresheyes-{target}')
            self.assertEqual(f'fresheyes-{target}-resume-guard', order[index - 1])
            self.assertEqual(f'fresheyes-{target}-halt-guard', order[index + 1])
            for guard in (order[index - 1], order[index + 1]):
                self.assertEqual('fail', step_field(step_section(guard), 'on_error'))


if __name__ == '__main__':
    unittest.main()
