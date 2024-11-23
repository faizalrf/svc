---
plugin: aws_ec2

regions:
{{ regions }}

filters:
 instance-state-name: 'running'
 tag:Project:
   - '{{ cluster_name }}'

groups:
  cassandra: (tags['Type'] is defined and tags['Type'] == 'Cassandra')
  aws_loader: (tags['Type'] is defined and tags['Type'] == 'CassandraLoader')
  cassandra_nonseed: (tags['Group'] is defined and tags['Group'] == 'CassandraNonSeed')
  cassandra_seed: (tags['Group'] is defined and tags['Group'] == 'CassandraSeed')
  cassandra_scale: (tags['Group'] is defined and tags['Group'] == 'CassandraScale')

keyed_groups:
  # Add hosts to tag_Name_Value groups for each Name/Value tag pair
  - prefix: tag
    key: tags
