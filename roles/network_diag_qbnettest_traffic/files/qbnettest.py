#!/usr/bin/python3

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import glob
import re
import random
import datetime

def create_ssh_remote(host_name, ssh_options, command):
  args = [
    'ssh',
    '-o StrictHostKeyChecking=no',
    '-q' ]
  args.extend(ssh_options);
  args.append(str(host_name))
  args.append("LC_ALL=en_US.UTF-8")
  args.append("sudo " + command + ' 2>&1')
  process = subprocess.Popen(args, stdout=subprocess.PIPE)
  return process

def wait_for_all(procs, sleepsecs):
  finished = False
  while not finished:
    finished = True
    for proc in procs:
      proc.poll()
      if proc.returncode == None:
        finished = False
    if not finished:
      time.sleep(sleepsecs)

def collect_sysctl(hosts, ssh_options, filename):
  print("Collecting sysctl network settings...", end='', flush=True)
  procs = list()
  for host in hosts:
    process = create_ssh_remote(host, ssh_options, "sysctl -a | grep ipv4")
    procs.append(process)

  wait_for_all(procs, 1)

  f = open(filename, "w")
  for i in range(0, len(procs)):
    f.write(str(hosts[i]) + " ***************************************************************************\n")
    for line in iter(procs[i].stdout.readline, b''):
      f.write(line.decode('ascii'))
    f.write("\n")
  f.close()
  print("done")

def collect_netstats(hosts, ssh_options, filename):
  print("Collecting network statistics...", end='', flush=True)
  procs = list()
  for host in hosts:
    process = create_ssh_remote(host, ssh_options, "ip -s address;nstat -z")
    procs.append(process)

  wait_for_all(procs, 1)

  f = open(filename, "w")
  for i in range(0, len(procs)):
    f.write(str(hosts[i]) + " ***************************************************************************\n")
    for line in iter(procs[i].stdout.readline, b''):
      f.write(line.decode('ascii'))
    f.write("\n")
  f.close()
  print("done")

def ping(host_pairs, ssh_options, block_size, f):
  procs = list()
  for (host_name, target) in host_pairs:
    process = create_ssh_remote(host_name, ssh_options, "ping -f -q -w 5 -s " + str(block_size) + " " + str(target))
    procs.append(process)

  wait_for_all(procs, 2)

  for i in range(0,len(procs)):
    (host_name,target) = host_pairs[i]
    if procs[i].returncode != 0:
      f.write(str(host_name) + ","  + str(target) + "," + str(block_size) + ",100,,,,,ping failed\n")
    pkg_loss = 100
    rtt_min = 0
    rtt_avg = 0
    rtt_max = 0
    rtt_mdev = 0
    for line in iter(procs[i].stdout.readline, b''):
      match = re.search("(\d+)% packet loss", str(line))
      if match is not None:
        pkg_loss = match.group(1)
      match = re.search("min\/avg\/max\/mdev\s+=\s+([\d\.]+)\/([\d\.]+)\/([\d\.]+)\/([\d\.]+)", str(line))
      if match is not None:
        rtt_min = match.group(1)
        rtt_avg = match.group(2)
        rtt_max = match.group(3)
        rtt_mdev = match.group(4)

    if int(pkg_loss) >= 100:
      f.write(str(host_name) + ","  + str(target) + "," + str(block_size) + "," + str(pkg_loss) + "\n")
    else:
      f.write(str(host_name) + ","  + str(target) + "," + str(block_size) + "," + str(pkg_loss) + "," + str(rtt_min) \
        + "," + str(rtt_avg) + "," + str(rtt_max) + "," + str(rtt_mdev) + ",\n")



def iperf_start_servers(host_pairs, ssh_options, buf_len):
  print("Starting iperf servers on all nodes...", end='', flush=True)
  servers = list()
  pids = list()
  for (host_name, target) in host_pairs:
    servers.append((host_name, create_ssh_remote(host_name, ssh_options, 'echo $(iperf -D -s -N -l ' + str(buf_len) +' 2>&1 | grep ID | cut -d":" -f 2 | tr -d "\n" | tr -d " ")')))

  time.sleep(2)

  for proc in servers:
    pid = proc[1].stdout.read().decode("ascii").rstrip()
    pids.append((proc[0], pid))

  # verify all processes are up and running
  for (host_name, pid) in pids:
    process = create_ssh_remote(host_name, ssh_options, 'kill -0 ' + str(pid))
    process.wait()
    if process.returncode != 0:
      print("Could not start iperf server in daemon mode on " + host_name)
      print(process.stdout.readlines())
      iperf_stop_servers(ssh_options, pids)
      raise Exception("Failed to start iperf servers. Aborting")

  print("done")
  return pids


def iperf_stop_servers(ssh_options, pids):
  print("Stopping iperf servers on all nodes...", end='', flush=True)
  for (host_name, pid) in pids:
    try:
      process = create_ssh_remote(host_name, ssh_options, 'kill ' + str(pid))
      process.wait()
    except:
      print("Could not stop iperf server on " + proc[0])
      pass
  print("done")

def iperf(host_pairs, ssh_options, block_size, f):
  servers = iperf_start_servers(host_pairs, ssh_options, block_size)

  print("Starting iperf test with buffer size " + str(block_size) + "...", end='', flush=True)
  procs = list()
  for (host_name, target) in host_pairs:
    procs.append(create_ssh_remote(host_name, ssh_options, "iperf -l " + str(block_size) +" -P 8 -N -t 30 -y c -c " + str(target)))

  wait_for_all(procs, 5)
  for i in range(0,len(procs)):
    (host_name,target) = host_pairs[i]
    if procs[i].returncode != 0:
      print("failed: " + host_name)
      print(procs[i].stdout.read())
      f.write(str(host_name) + ","  + str(target) + "," + str(block_size) + ",,,,iperf failed\n")
    else:
      result = next(csv.reader([procs[i].stdout.read().decode("ascii")]))
      f.write(str(host_name) + ","  + str(target) + "," + str(block_size) + "," + str(result[6]) + "," + str(result[7]) + "," + str(result[8]) + ",\n")

  print("done")

  iperf_stop_servers(ssh_options, servers)

def iperf_1toN(hosts, ssh_options, f):
  host_pairs = [(host,"") for host in hosts]
  servers = iperf_start_servers(host_pairs, ssh_options, 128 * 1024)

  for host in hosts:
    targets = list()
    others = list(hosts)
    others.remove(host)
    num_remote = min(8, len(hosts) - 1)
    for i in range(0, num_remote):
      rnd_index = random.randrange(0, len(others))
      targets.append(others[rnd_index])
      del others[rnd_index]
    print("1-to-N iperf test to " + host + " from " + str(targets) + "...", end='', flush=True)
    procs = list()
    for target in targets:
      procs.append(create_ssh_remote(target, ssh_options, "iperf -l 131072 -P 4 -N -t 20 -y c -c " + str(host)))

    wait_for_all(procs, 5)
    sum_bps = 0
    sum_bytes = 0
    for i in range(0,len(procs)):
      if procs[i].returncode != 0:
        print("failed on " + host + " to " + targets[i])
        print(procs[i].stdout.read())
        f.write(str(host) + ","  + str(targets[i]) + ",,,,iperf failed\n")
      else:
        result = next(csv.reader([procs[i].stdout.read().decode("ascii")]))
        sum_bps = sum_bps + int(result[8])
        sum_bytes = sum_bytes + int(result[7])
        f.write(str(host) + ","  + str(targets[i]) + ",131072," + str(result[6]) + "," + str(result[7]) + "," + str(result[8]) + ",\n")
    f.write(str(host) + ",SUM,\"\",\"\"," + str(sum_bytes) + "," + str(sum_bps) + ",\n")
    f.flush()

    print("done")

  iperf_stop_servers(ssh_options, servers)

if __name__ == '__main__':
  parser = argparse.ArgumentParser()

  parser.add_argument('-H', '--hosts', type=argparse.FileType('r'), required=True)
  parser.add_argument('-u', '--username', type=str, default="root")
  parser.add_argument('-i', '--identity', type=str)

  parsed = parser.parse_args()

  sshopts = [ "-l", parsed.username ]
  if parsed.identity is not None:
    sshopts.append("-i")
    sshopts.append(parsed.identity)

  hosts = parsed.hosts.read().splitlines()
  outputdir = "qbnettest-results-" + datetime.datetime.now().strftime('%Y%m%d%H%M%S')
  os.mkdir(outputdir)

  collect_sysctl(hosts,sshopts,outputdir + "/sysctl_ipv4.txt")

  collect_netstats(hosts,sshopts,outputdir + "/netstats_pre.txt")

  ping_hosts = list()
  for host in hosts:
    others = list(hosts)
    others.remove(host)
    remote_host = others[random.randrange(0,len(others))]
    ping_hosts.append([host, remote_host])

  pingfile = open(outputdir + "/ping.csv", "w")
  pingfile.write("# Command executed: ping -f -q -w 5 -s <payload bytes> <remote host>\n")
  pingfile.write("host,target,\"payload bytes\",\"packet loss\",\"rtt min ms\",\"rtt avg ms\",\"rtt max ms\",\"rtt mdev ms\",error\n")
  for bs in [1024, 4096 + 50, 8192 + 52, 4 * 4096 + 56]:
    print("Testing flood ping with message size " + str(bs) + "...")
    ping(ping_hosts, sshopts, bs, pingfile)
  pingfile.close()

  collect_netstats(hosts,sshopts,outputdir + "/netstats_post_ping.txt")

  iperf_hosts = list()
  reverse_hosts = hosts[::-1]
  for i in range(0, len(hosts)):
    iperf_hosts.append([hosts[i], reverse_hosts[i]])

  iperffile = open(outputdir + "/iperf_1to1.csv", "w")
  iperffile.write("# Command executed: iperf -l <buffer size> -P 8 -N -t 30 -y c -c <server> \n")
  iperffile.write("host,target,\"buffer size\",\"interval s\",\"bytes transfered\",\"bits per second\",comment\n")
  for bs in [4096 + 50, 8192 + 52, 4 * 4096 + 56, 1048576]:
    print("Testing iperf with message size " + str(bs) + "...")
    iperf(iperf_hosts, sshopts, bs, iperffile)
    iperffile.flush()
  iperffile.close()

  collect_netstats(hosts,sshopts,outputdir + "/netstats_post_iperf1to1.txt")

  iperffile = open(outputdir + "/iperf_1toN.csv", "w")
  iperffile.write("host,target,\"buffer size\",\"interval s\",\"bytes transfered\",\"bits per second\",comment\n")
  iperf_1toN(hosts, sshopts, iperffile)
  iperffile.flush()
  iperffile.close()

  collect_netstats(hosts,sshopts,outputdir + "/netstats_post_iperf1toN.txt")

  subprocess.call(["tar", "-czf", outputdir + ".tar.gz", outputdir])
  shutil.rmtree(outputdir)

  print ("Done.")
