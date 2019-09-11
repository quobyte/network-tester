# Network tester #


This is a network tester playbook, which uses HP Netperf and Flent under the hood. The test is based on a mixed TCP/UDP/ICMP workload that is executed over three different client-server set configurations (1xM, Nx1, NxM). This software requires ansible >= 2.4 and python 3.6. The playbook has tested on the following OS platforms: RHEL/CentOS 7.x and Ubuntu 18.04.

## Preparations ##

Before you run the test make sure you can access all hosts via SSH. We recommend using SSH keys for authentication, although passwords also can be used. You may rely on your current SSH client configuration or provide authentication data explicitly in the file `group_vars/netdiag_hosts.yaml`. Refer to [Ansible documentation](https://docs.ansible.com/ansible/latest/user_guide/intro_inventory.html#list-of-behavioral-inventory-parameters) for further information.

Host are divided into two sets: clients and servers. The sets may overlap, but since this playbook is about network testing disjoint set configuration is recommended. Populate inventory file accordingly.

To verify configuration is correct run the following:

```
$ ansible -i inventory_file -m ping -b all
```

The command must produce no errors.

The playbook includes a Netperf RPM package for RHEL/CentOS 7.x for your convenience. If you would like to provide your own binaries, bear in mind *--enable-demo* option must be supported by Netperf. In that case set `netperf_install: False`.

Due to extensive use of sockets a user on behalf which tests are executed should be granted very high or unlimited file descriptor limits on target hosts.

## Test execution ##

To run the test:

```
$ ansible-playbook -i inventory_file netdiag.yaml
```

You can also split that into three phases:

```
$ ansible-playbook -i inventory_file netdiag.yaml -t install
$ ansible-playbook -i inventory_file netdiag.yaml -t test
$ ansible-playbook -i inventory_file netdiag.yaml -t cleanup
```

Test results are stored on an ansible host at `/tmp/quobyte_netdiag_data`.

Current and prospective Quobyte customers may create a [ticket](https://tickets.quobyte.com) and upload test results for further analysis.


### Host stack monitoring ###

A stripped down version of the *netdiag* playbook can be used for host stack monitoring under production load. The name of the relevant playbook is *get.kernel.data.yaml*.

```
$ ansible-playbook -i inventory_file netdiag.yaml -t install
$ ansible-playbook -i inventory_file get.kernel.data.yaml -e stats_interval=120
$ ansible-playbook -i inventory_file netdiag.yaml -t cleanup
```

The variable *stats_interval* defines period between two consecutive diagnostic probes launched on target hosts. By default it is 60 seconds.

## Legal notice ##

Product names and brands found in the repository are property of their respective owners. The playbook is distributed under Apache License 2.0.
