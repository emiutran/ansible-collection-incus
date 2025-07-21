#!/usr/bin/python
# -*- coding: utf-8 -*-
# (c) 2024, Peter Magnusson <me@kmpm.se>
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = '''
---
module: incus_network_forward
author: "Emily Tran (@eutran)"
short_description: Manage Incus Network Forwards
description:
  - Management of Incus Network Forwards
attributes:
    check_mode:
        support: full
    diff_mode:
        support: full
options:
    network:
        description:
            - Name of the network that the network forward uses
        type: str
        required: true
    description:
        description:
            - A description associated with this network forward
        type: str
        required: false
    config:
        description:
            - The set of config options for the network forward
        type: dict
        required: false
    project:
        description:
            - Project the network forward is part of
        type: str
        default: default    
    ports:
        description: List of port forwarding rules    
        type: list
        elements: dict
        required: false
    listener_address:
        description: IP Address to listen on
        type: str
        required: true
    state:
        description:
            - State of the network forward
        type: str
        choices: [present, absent]
        default: present
'''

EXAMPLES = '''
---
- hosts: localhost
  connection: local
  tasks:
    - network: Create network forward
      kmpm.incus.incus_network_forward:
        network: my-network
        listen_address: 10.150.19.10
        config:
          target_address: 10.150.19.111
        ports:
        - protocol: tcp
          listen_port: "22"
          target_port: "2022"
          target_address: "10.150.19.112"
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


class IncusNetworkForwardManagement(object):
    def __init__(self, module, **kwargs):
        self.module = module

        self.network = self.module.params['network']
        self.description = self.module.params['description']
        self.config = self.module.params['config']
        self.ports = self.module.params['ports']
        self.listen_address = self.module.params['listen_address']        
        self.project = self.module.params['project']
        self.state = self.module.params['state']

        self.debug = self.module._verbosity >= 3

        try:
            self.client = IncusClient(
                project=self.project,
                debug=self.debug
            )
        except IncusClientException as e:
            self.module.fail_json(msg=e.msg)

        self.diff = {'before': {}, 'after': {}}

    def _get_network_forwards(self):
        url = '/1.0/networks/{0}/forwards'.format(self.network)
        return self.client.query_raw('GET', url, ok_errors=[404])

    # Drive the state of the network forward to match the specified state, creating or
    # updating it as necessary.
    def _present(self):
        method = 'POST'

        if self.diff['before']['state'] == "present":
            method = 'PATCH'

        payload = {
            'listen_address': self.listen_address,
            'description': self.description,
            'config': self.config or {},
            'ports': self.ports or [],
        }

        match method:
            case 'POST':
                url = '/1.0/network/{0}/forwards'.format(self.network)
            case 'PATCH':
                url = '/1.0/network/{0}/forwards/{1}'.format(self.network,self.listen_address)
            case _:
                raise Exception("invalid state")

        if not self.module.check_mode:
            return self.client.query_raw(method, url, payload=payload)

    # Ensure the network forward does not exist.
    def _absent(self):
        if self.diff['before']['state'] == "absent":
            return

        url = '/1.0/network/{0}/forwards/{1}'.format(self.network,self.listen_address)

        if not self.module.check_mode:
            return self.client.query_raw('DELETE', url)

    def run(self):
        try:
            current = self._get_network_forwards()

            # Set the before / after states for the diff output.
            self.diff['before']['forward'] = current['metadata']
            self.diff['before']['state'] = _incus_to_module_state(current)

            # Map the current state to an action.
            action = getattr(self, ACTION_DISPATCH[self.state])
            action()

            # Refresh the server state after the action was completed.
            current = self._get_network_forwards()
            self.diff['after']['forward'] = current['metadata']
            self.diff['after']['state'] = _incus_to_module_state(current)

            state_changed = self.diff['before']['forward'] != self.diff['after']['forward']
            result_json = {
                'log_verbosity': self.module._verbosity,
                'changed': state_changed,
                'old_state': self.diff['before']['state'],
                'diff': self.diff,
                'forward': self.diff['after']['forward'],
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
            network=dict(type='str', required=True),
            description=dict(type='str', required=False),
            config=dict(type='dict', required=False),
            ports=dict(type='list', elements='dict', required=False),
            listen_address=dict(type='str', required=True)
            project=dict(type='str', default='default'),
            state=dict(type='str', default='present', choices=['present', 'absent']),
        ),
        supports_check_mode=True
    )

    resource_manager = IncusNetworkForwardManagement(module=module)
    resource_manager.run()


if __name__ == '__main__':
    main()
