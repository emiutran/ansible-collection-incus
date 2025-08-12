#!/usr/bin/python
# -*- coding: utf-8 -*-
# (c) 2024, Peter Magnusson <me@kmpm.se>
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = '''
---
module: incus_network_peer
author: "Emily Tran (@memiutran)"
short_description: Manage Incus Network Peers
description:
  - Management of Incus Network Peers to enable network peering between OVN networks in Incus
attributes:
    check_mode:
        support: full
    diff_mode:
        support: full
options:
    name:
        description:
            - Name of the Peer 
        type: str
        required: true
    network:
        description:
            - Name of local OVN network name
        type: str
        required: true
    target_network:
        description:
            - Name of Target local network peer name
        type: str
        required: false
    description:
        description:
            - A description associated with this peer
        type: str
        required: false
    config:
        description:
            - The set of config entries for the network peer
        type: dict
        required: false
    type:
        description:
            - Type of network peering
        type: str
        required: false
    target_integration:
        description:
            - Integration name for remote peers
        type: str
        required: false
    target_project:
        description:
            - Project the target network exists
        type: str
        required: false
    project:
        description:
            - Project the local network exists
        type: str
        default: default
    state:
        description:
            - State of the network peer
        type: str
        choices: [present, absent]
        default: present
'''

EXAMPLES = '''
# Create a local peer between default ovn and test-ovn
- host: localhost
  connection: local
  tasks:
    - name: Create network peer 1/2
      kmpm.incus.incus_network_peer:
        name: default-test-ovn
        network: default
        target_network: test-ovn
        target_project: default
        description: "Peering OVN networkings default and test-ovn part 1
        state: present
    - name: Create network peer 2/2
      kmpm.incus.incus_network_peer:
        name: test-ovn-default
        network: test-ovn
        target_network: default
        target_project: default
        description: "Peering OVN networkings default and test-ovn part 2
        state: present
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.kmpm.incus.plugins.module_utils.incuscli import (
    IncusClient, IncusClientException)

# A map of desired state -> handler method.
ACTION_DISPATCH = {
    'present': '_present',
    'absent': '_absent'
}


class IncusNetworkPeerManagement(object):
    def __init__(self, module, **kwargs):
        self.module = module

        self.name = self.module.params['name']
        self.network = self.module.params['network']
        self.target_network = self.module.params['target_network']
        self.description = self.module.params['description']
        self.config = self.module.params['config']
        self.type = self.module.params['type']
        self.target_integration = self.module.params['target_integration']
        self.target_project = self.module.params['target_project']
        self.project = self.module.params['project']
        self.state = self.module.params['state']
        self.actions = []

        self.debug = self.module._verbosity >= 3

        try:
            self.client = IncusClient(
                project=self.project,
                debug=self.debug
            )
        except IncusClientException as e:
            self.module.fail_json(msg=e.msg)

        self.diff = {'before': {}, 'after': {}}

    def _get_peer(self):
        """ Get single network peer for a network """
        url = '/1.0/networks/{0}/peers/{1}'.format(self.network, self.name)
        return self.client.query_raw('GET', url, ok_errors=[404])
    def _get_peers(self):
        """ Get network peer list for a network """
        url = '/1.0/networks/{0}/peers'.format(self.network)
        return self.client.query_raw('GET', url, ok_errors=[404])

    # Drive the state of the network peer to match the specified state, creating or
    # updating it as necessary.
    def _present(self):
        method = 'POST'

        if self.diff['before']['state'] == "present":
            method = 'PATCH'

        payload = {
            'name': self.name, 
            'config': self.config,
            'description': self.description,
        }

        if self.target_network:
            payload['target_network'] = self.target_network
            if self.target_project:
                payload['target_project'] = self.target_project
        if self.target_integration:
            payload['target_integration'] = self.target_integration
        if self.type:
            payload['type'] = self.type

        if method == 'POST':
            url = '/1.0/networks/{0}/peers'.format(self.network)
        else:
            url = '/1.0/networks/{0}/peers/{1}'.format(self.network, self.name)

        if not self.module.check_mode:
            res = self.client.query_raw(method, url, payload=payload)
        else:
            res = None

        self.actions.append('create' if method == 'POST' else 'update')
        return res

    # Ensure the network Peer does not exist.
    def _absent(self):
        if self.diff['before']['state'] == "absent":
            return
        url = '/1.0/networks/{0}/peers/{1}'.format(self.network, self.name)
        if not self.module.check_mode:
            return self.client.query_raw('DELETE', url)
        self.actions.append('delete')

    def run(self):
        try:
            current = self._get_peer()

            # Set the before / after states for the diff output.
            self.diff['before']['peer'] = current['metadata']
            self.diff['before']['state'] = _incus_to_module_state(current)

            # Map the current state to an action.
            action = getattr(self, ACTION_DISPATCH[self.state])
            action()

            # Refresh the server state after the action was completed.
            current = self._get_peer()
            self.diff['after']['peer'] = current['metadata']
            self.diff['after']['state'] = _incus_to_module_state(current)

            state_changed = self.diff['before']['peer'] != self.diff['after']['peer']
            result_json = {
                'log_verbosity': self.module._verbosity,
                'changed': state_changed,
                'old_state': self.diff['before']['state'],
                'diff': self.diff,
                'peer': self.diff['after']['peer'],
            }
            if self.debug:
                result_json['logs'] = self.client.logs

            self.module.exit_json(**result_json)

        except IncusClientException as e:
            fail_params = {
                'msg': e.msg,
                'changed': False,
                'diff': self.diff
            }
            if self.client.debug:
                fail_params['logs'] = self.client.logs
            self.module.fail_json(**fail_params)

def _incus_to_module_state(resp_json):
    if resp_json['status_code'] == 200:
        return 'present'
    if resp_json['error_code'] == 404:
        return 'absent'
    raise Exception("unknown resource state")

def main():
    '''Ansible Main module.'''

    module = AnsibleModule(
        argument_spec=dict(
            name=dict(type='str', required=True),
            network=dict(type='str', required=True),
            target_network=dict(type='str', required=True),
            description=dict(type='str', required=False),
            config=dict(type='dict', required=False),
            type=dict(type='str', required=False),
            target_integration=dict(type='str', required=False),
            target_project=dict(type='str', required=False),
            project=dict(type='str', default='default'),
            state=dict(type='str', default='present', choices=['present', 'absent']),
        ),
        supports_check_mode=True
    )

    resource_manager = IncusNetworkPeerManagement(module=module)
    resource_manager.run()


if __name__ == '__main__':
    main()
