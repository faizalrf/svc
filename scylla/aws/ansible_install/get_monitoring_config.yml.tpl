---
- name: Install Scylla on nodes
  hosts: scylla
  any_errors_fatal: true
  tasks:
    - name: Get Scylla Monitoring scripts
      ansible.builtin.shell: |
        rm -f genconfig* scylla_servers.yml
        wget https://raw.githubusercontent.com/scylladb/scylla-monitoring/master/genconfig.py
      run_once: true

    - name: Generate Scylla Monitoring configuration file remotely
      ansible.builtin.shell: |
        nodetool status | python3 genconfig.py -NS -c '{{ cluster_name }}'
      run_once: true

    - name: Copy scylla_servers.yml to local
      ansible.builtin.fetch:
        src: "/home/ubuntu/scylla_servers.yml"
        dest: "./"
        flat: yes
      run_once: true
      register: a