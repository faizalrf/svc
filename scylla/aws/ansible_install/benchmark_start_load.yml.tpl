- name: Initiate ingestion for benchmark
  hosts: aws_loader
  tasks:
  {{ insert_populate_tasks_here }}
  - name: Start cassandra-stress population on all loaders in parallel
    shell: |
      {{ insert_command }}
  - name: Start cassandra-stress on all loaders in parallel
    shell: |
      {{ command }}

