#!/usr/bin/python
# -*- coding: utf-8 -*-
# (c) 2024, Peter Magnusson <me@kmpm.se>
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = '''
---
module: incus_network_zone
author: "Emily Tran (@)"
short_description: Manage Incus Network Zones
description:
  - Create or delete Incus Network Zones using the Incus REST API.
options:
  name:
    description:
      - Name of the network zone.
    required: true
    type: str
  description:
    description:
      - Description of the network zone.
    required: false
    type: str
  config:
    description:
      - Dictionary of network zone configuration options.
    required: false
    type: dict
  project:
    description:
      - Project name (defaults to "default").
    required: false
    type: str
    default: default
  state:
    description:
      - Whether the network zone should be present or absent.
    choices: [present, absent]
    default: present
    type: str
'''

EXAMPLES = '''
- host: localhost
  connection: local
  tasks:
    - name: Create a network zone
      kmpm.incus.incus_network_zone:
        name: custom.example.org
        description: My custom DNS zone
        config:
          dns.nameservers: incus.example.net
          peers.ns.address: 127.0.0.1
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


class IncusNetworkZoneManagement(object):
    def __init__(self, module, **kwargs):
        self.module = module

        self.name = self.module.params['name']
        self.project = self.module.params['project']
        self.description = self.module.params['description']
        self.config = self.module.params['config']
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

    def _get_network_zone(self):
        url = '/1.0/network-zones/{0}'.format(self.name)
        return self.client.query_raw('GET', url, ok_errors=[404])

    # Drive the state of the Network zones to match the specified state, creating or
    # updating it as necessary.
    def _present(self):
        method = 'POST'

        if self.diff['before']['state'] == "present":
            method = 'PATCH'

        payload = {
            'name': self.name, 
            'description': self.description,
            'config': self.config,
        }

        match method:
            case 'POST':
                url = '/1.0/network-zones'
            case 'PATCH':
                url = '/1.0/network-zones/{0}'.format(self.name)
            case _:
                raise Exception("invalid state")

        if not self.module.check_mode:
            return self.client.query_raw(method, url, payload=payload)

    # Ensure the network zone does not exist.
    def _absent(self):
        if self.diff['before']['state'] == "absent":
            return

        url = '/1.0/network-zones/{0}'.format(self.name)

        if not self.module.check_mode:
            return self.client.query_raw('DELETE', url)

    def run(self):
        try:
            current = self._get_network_zone()

            # Set the before / after states for the diff output.
            self.diff['before']['zone'] = current['metadata']
            self.diff['before']['state'] = _incus_to_module_state(current)

            # Map the current state to an action.
            action = getattr(self, ACTION_DISPATCH[self.state])
            action()

            # Refresh the server state after the action was completed.
            current = self._get_network_zone()
            self.diff['after']['zone'] = current['metadata']
            self.diff['after']['state'] = _incus_to_module_state(current)

            state_changed = self.diff['before']['zone'] != self.diff['after']['zone']
            result_json = {
                'log_verbosity': self.module._verbosity,
                'changed': state_changed,
                'old_state': self.diff['before']['state'],
                'diff': self.diff,
                'zone': self.diff['after']['zone'],
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
            description=dict(type='str', required=False),
            config=dict(type='dict', required=False),
            project=dict(type='str', default='default'),
            state=dict(type='str', default='present', choices=['present', 'absent']),
        ),
        supports_check_mode=True
    )

    resource_manager = IncusNetworkZoneManagement(module=module)
    resource_manager.run()


if __name__ == '__main__':
    main()
