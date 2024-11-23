---
plugin: aws_ec2

regions:
{{ regions }}

filters:
 instance-state-name: 'running'
 tag:Project:
   - '{{ cluster_name }}'

# Scylla_scale added, Faisal, 2024-08-08
groups:
  scylla: (tags['Type'] is defined and tags['Type'] == 'Scylla')
  aws_loader: (tags['Type'] is defined and tags['Type'] == 'Loader')
  aws_monitor: (tags['Type'] is defined and tags['Type'] == 'Monitoring')
  scylla_nonseed: (tags['Group'] is defined and tags['Group'] == 'NonSeed')
  scylla_seed: (tags['Group'] is defined and tags['Group'] == 'Seed')
  scylla_scale: (tags['Group'] is defined and tags['Group'] == 'ScyllaScale')
  scylla_seed2: (tags['Group'] is defined and tags['Group'] == 'Seed2')

keyed_groups:
  # Add hosts to tag_Name_Value groups for each Name/Value tag pair
  - prefix: tag
    key: tags
