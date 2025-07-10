#!/usr/bin/python
# -*- coding: utf-8 -*-
# (c) 2024, Peter Magnusson <me@kmpm.se>
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = '''
---
module: incus_network_load_balancer
author: "Emily Tran (@emiutran)"
short_description: Manage Incus Network Load Balancer
description:
  - Management of Incus Network Load Balancer
attributes:
    check_mode:
        support: full
    diff_mode:
        support: full
options:
    name:
        description:
            - Name of the Load Balancer
        type: str
        required: true
    description:
        description:
            - A description associated with this Load Balancer
        type: str
        required: false
    config:
        description:
            - The set of config entries for the network Load Balancer
        type: dict
        required: false
    backends:
        description:
          - List of backends dictionaries (name, target_address, description).
        type: array
        required: false
    ports:
        description:
          - List of port mappings (description, protocol, listen_port, target_backend).
        type: array
        required: false
    listen_address:
        description:
          - the IP address the Load Balancer listens on.
        type: array
        required: false
    state:
        description:
            - State of the network Load Balancer
        type: str
        choices: [present, absent]
        default: present
'''
EXAMPLES = '''
- host: localhost
  connection: local
  tasks:
    - name: Create a load balancer
      kmpm.incus.incus_network_load_balancer:
        network: default
        listen_address: 10.10.10.200
        description: Load balancer
        config:
          healthcheck: "true"
          healthcheck.interval: "10"
        backends:
          - name: instance01
            target_address: 10.0.0.10
          - name: instance02
            target_address: 10.0.0.11
          - name: instance03
            target_address: 10.0.0.12
        ports:
          - description: SSH
            protocol: tcp
            listen_port: 22
            target_backend:
              - instance01
              - instance02
              - instance03
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.kmpm.incus.plugins.module_utils.incuscli import (
    IncusClient, IncusClientException)

# A map of desired state -> handler method.
ACTION_DISPATCH = {
    'present': '_present',
    'absent': '_absent'
}


class IncusNetworkLoadBalancerManagement(object):
    def __init__(self, module, **kwargs):
        self.module = module

        self.network = self.module.params['network']
        self.listen_address = self.module.params['listen_address']
        self.description = self.module.params['description']
        self.config = self.module.params['config'] or {}
        self.backends = self.module.params['backends'] or []
        self.ports = self.module.params['ports'] or []
        self.state = self.module.params['state']

        self.debug = self.module._verbosity >= 3

        try:
            self.client = IncusClient(debug=self.debug)
        except IncusClientException as e:
            self.module.fail_json(msg=e.msg)

        self.diff = {'before': {}, 'after': {}}

    def _get_lb(self):
        url = '/1.0/networks/{0}/load-balancers/{1}'.format(self.network,self.listen_address)
        return self.client.query_raw('GET', url, ok_errors=[404])

    # Drive the state of the Load Balancer to match the specified state, creating or
    # updating it as necessary.
    def _present(self):
        method = 'POST'

        if self.diff['before']['state'] == "present":
            method = 'PATCH'

        payload = {
            'listen_address': self.listen_address,
            'description': self.description,
            'network': self.network,
            'config': self.config,
            'backends': self.backends,
            'ports': [
                {
                    **port,
                    'listen_port': str(port['listen_port'])
                }
                for port in self.ports
            ],
        }

        match method:
            case 'POST':
                url = '/1.0/networks/{0}/load-balancers'.format(self.network)
            case 'PATCH':
                url = '/1.0/networks/{0}/load-balancers/{1}'.format(self.network,self.listen_address)
            case _:
                raise Exception("invalid state")

        if not self.module.check_mode:
            return self.client.query_raw(method, url, payload=payload)

    # Ensure the Load Balancer does not exist.
    def _absent(self):
        if self.diff['before']['state'] == "absent":
            return

        url = '/1.0/networks/{0}/load-balancers/{1}'.format(self.network,self.listen_address)

        if not self.module.check_mode:
            return self.client.query_raw('DELETE', url)

    def run(self):
        try:
            current = self._get_lb()

            # Set the before / after states for the diff output.
            self.diff['before']['loadbalancer'] = current['metadata']
            self.diff['before']['state'] = _incus_to_module_state(current)

            # Map the current state to an action.
            action = getattr(self, ACTION_DISPATCH[self.state])
            action()

            # Refresh the server state after the action was completed.
            current = self._get_lb()
            self.diff['after']['loadbalancer'] = current['metadata']
            self.diff['after']['state'] = _incus_to_module_state(current)

            state_changed = self.diff['before']['loadbalancer'] != self.diff['after']['loadbalancer']
            result_json = {
                'log_verbosity': self.module._verbosity,
                'changed': state_changed,
                'old_state': self.diff['before']['state'],
                'diff': self.diff,
                'loadbalancer': self.diff['after']['loadbalancer'],
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
            network=dict(type="str", required=True),
            listen_address=dict(type="str", required=True),
            description=dict(type="str"),
            config=dict(type="dict", default={}),
            backends=dict(type="list", elements="dict", default=[]),
            ports=dict(type="list", elements="dict", default=[]),
            state=dict(type="str", choices=["present", "absent"], default="present"),
        ),
        supports_check_mode=True
    )

    resource_manager = IncusNetworkLoadBalancerManagement(module=module)
    resource_manager.run()


if __name__ == '__main__':
    main()

