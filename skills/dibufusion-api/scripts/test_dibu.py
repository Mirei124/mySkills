"""Offline regressions; no credentials, live API calls, or workload mutations."""
import copy
import unittest
from unittest.mock import patch

import dibu


class DibuTests(unittest.TestCase):
    def test_create_rejects_blank_password_and_mismatched_gpu_count(self):
        body = {'password': '', 'is_VM': False, 'cmd': 'echo ok', 'num_gpu': 2,
                'gpu_selection': {'count': 2}}
        with self.assertRaisesRegex(ValueError, 'password'):
            dibu.prepare('container-create', {}, body)
        body['password'] = 'fixture-not-a-real-password'
        body['gpu_selection']['count'] = 1
        with self.assertRaisesRegex(ValueError, 'num_gpu'):
            dibu.prepare('container-create', {}, body)
        body['gpu_selection']['count'] = 2
        self.assertEqual(dibu.prepare('container-create', {}, body)[3]['num_gpu'], 2)

    def test_task_requires_command_but_experiment_does_not(self):
        body = {'password': 'fixture', 'is_VM': False, 'cmd': ''}
        with self.assertRaisesRegex(ValueError, 'cmd'):
            dibu.prepare('container-create', {}, body)
        body['is_VM'] = True
        dibu.prepare('container-create', {}, body)

    def test_preview_redacts_nested_secrets_without_modifying_request(self):
        body = {'password': 'private', 'nested': {'accessToken': 'private-token'}, 'cmd': 'echo ok'}
        result = dibu.redact(body)
        self.assertEqual(result['password'], '[REDACTED]')
        self.assertEqual(result['nested']['accessToken'], '[REDACTED]')
        self.assertEqual(body['password'], 'private')
        self.assertEqual(result['cmd'], 'echo ok')

    def test_availability_excludes_disabled_nodes_and_keeps_unknown(self):
        dashboard = {'stale': False, 'errors': {}, 'sampled_at_ms': 100,
                     'nodes': [{'node_id': 1, 'node_status': 'Ready', 'gpu_remain_num': 3},
                               {'node_id': 2, 'node_status': 'SchedulingDisabled', 'gpu_remain_num': 8},
                               {'node_id': 3, 'node_status': 'Ready', 'gpu_remain_num': None}]}
        result = dibu.resource_summary(dashboard)
        self.assertEqual([n['schedulable_free_gpus'] for n in result['nodes']], [3, None, None])
        stale = copy.deepcopy(dashboard)
        stale['stale'] = True
        self.assertTrue(all(n['schedulable_free_gpus'] is None for n in dibu.resource_summary(stale)['nodes']))

    def test_resource_summary_only_requests_dashboard(self):
        with patch.object(dibu, 'auth_config', return_value=('http://fixture', 'fixture')), patch.object(dibu, 'request', return_value={'nodes': [], 'stale': False}) as request:
            dibu.run_summary('resource-summary', {})
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[3], '/node/dashboard/')

    def test_task_status_searches_pages_and_reports_actual_status_and_events(self):
        calls = []
        def fake_request(base, auth, op, path, q, b, headers):
            calls.append((path, dict(q)))
            if path == '/container/getPodEvent/':
                return {'events': {'pod': [{'reason': 'FailedScheduling'}]}}
            if q['operate_id'] == 1 and q['page'] == 1:
                return {'results': [{'container_id': 1}], 'next': 'next-page'}
            if q['operate_id'] in (1, 2):
                return {'results': [{'container_id': 42, 'status': 'Pending', 'password': 'must-not-return'}], 'next': None}
            return {'results': [], 'next': None}
        with patch.object(dibu, 'auth_config', return_value=('http://fixture', 'fixture')), patch.object(dibu, 'request', side_effect=fake_request):
            result = dibu.run_summary('task-status', {'container_id': 42})
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['tasks'][0]['status'], 'Pending')
        self.assertNotIn('password', result['tasks'][0])
        self.assertEqual(result['events']['pod'][0]['reason'], 'FailedScheduling')
        self.assertTrue(any(q.get('page') == 2 for _, q in calls))

if __name__ == '__main__':
    unittest.main()
