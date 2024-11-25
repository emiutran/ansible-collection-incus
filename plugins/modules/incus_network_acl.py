#!/usr/bin/python
# -*- coding: utf-8 -*-
# (c) 2024, Peter Magnusson <me@kmpm.se>
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = '''
---
module: incus_network_acl
author: "Dom Dwyer (@domodwyer)"
short_description: Manage Incus Network ACLs
description:
  - Management of Incus Network ACLs
attributes:
    check_mode:
        support: full
    diff_mode:
        support: full
options:
    name:
        description:
            - Name of the ACL
        type: str
        required: true
    project:
        description:
            - Project the ACL is part of
        type: str
        default: default
    description:
        description:
            - A description associated with this ACL
        type: str
        required: false
    config:
        description:
            - The set of config entries for the network ACL
        type: dict
        required: false
    ingress:
        description:
          - The set of ingress rules as an array of dictionaries.
        type: array
        required: false
    egress:
        description:
          - The set of egress rules as an array of dictionaries.
        type: array
        required: false
    state:
        description:
            - State of the network ACL
        type: str
        choices: [present, absent]
        default: present
'''

EXAMPLES = '''
- host: localhost
  connection: local
  tasks:
    - name: Create network ACL
      kmpm.incus.incus_network_acl:
        name: restricted-network
        description: Restrict to 172.16.0.0/12
        ingress:
          - action: allow
            state: enabled
        egress:
          - action: allow
            description: Allow connection only this IP range.
            destination: "172.16.0.0/12"
            state: enabled
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


class IncusNetworkAclManagement(object):
    def __init__(self, module, **kwargs):
        self.module = module

        self.name = self.module.params['name']
        self.project = self.module.params['project']
        self.description = self.module.params['description']
        self.config = self.module.params['config']
        self.ingress = self.module.params['ingress']
        self.egress = self.module.params['egress']
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

    def _get_acl(self):
        url = '/1.0/network-acls/{0}'.format(self.name)
        return self.client.query_raw('GET', url, ok_errors=[404])

    # Drive the state of the ACL to match the specified state, creating or
    # updating it as necessary.
    def _present(self):
        method = 'POST'

        if self.diff['before']['state'] == "present":
            method = 'PATCH'

        payload = {
            'name': self.name, # Unused by PATCH / update requests
            'config': self.config,
            'description': self.description,
            'egress': self.egress,
            'ingress': self.ingress,
        }

        match method:
            case 'POST':
                url = '/1.0/network-acls'
            case 'PATCH':
                url = '/1.0/network-acls/{0}'.format(self.name)
            case _:
                raise Exception("invalid state")

        if not self.module.check_mode:
            return self.client.query_raw(method, url, payload=payload)

    # Ensure the ACL does not exist.
    def _absent(self):
        if self.diff['before']['state'] == "absent":
            return

        url = '/1.0/network-acls/{0}'.format(self.name)

        if not self.module.check_mode:
            return self.client.query_raw('DELETE', url)

    def run(self):
        try:
            current = self._get_acl()

            # Set the before / after states for the diff output.
            self.diff['before']['acl'] = current['metadata']
            self.diff['before']['state'] = _incus_to_module_state(current)

            # Map the current state to an action.
            action = getattr(self, ACTION_DISPATCH[self.state])
            action()

            # Refresh the server state after the action was completed.
            current = self._get_acl()
            self.diff['after']['acl'] = current['metadata']
            self.diff['after']['state'] = _incus_to_module_state(current)

            state_changed = self.diff['before']['acl'] != self.diff['after']['acl']
            result_json = {
                'log_verbosity': self.module._verbosity,
                'changed': state_changed,
                'old_state': self.diff['before']['state'],
                'diff': self.diff,
                'acl': self.diff['after']['acl'],
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
            project=dict(type='str', default='default'),
            description=dict(type='str', required=False),
            config=dict(type='dict', required=False),
            ingress=dict(type='list', required=False),
            egress=dict(type='list', required=False),
            state=dict(type='str', default='present', choices=['present', 'absent']),
        ),
        supports_check_mode=True
    )

    resource_manager = IncusNetworkAclManagement(module=module)
    resource_manager.run()


if __name__ == '__main__':
    main()
