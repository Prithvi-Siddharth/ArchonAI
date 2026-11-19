/**
 * Which official AWS Architecture Icon (src/assets/aws-icons, see NOTICE.md) belongs to a service
 * name or a data-flow label. Names are free text and often combine services ("Amazon CloudFront +
 * AWS WAF", "Amazon ECS (Fargate) + Auto Scaling"), so a name is split into parts and each part is
 * matched on its own. A part with no confident match gets no icon: nothing is guessed.
 */

export interface AwsIcon {
  /** File name in src/assets/aws-icons, without ".svg". */
  key: string
  /** The service's name, for the legend. */
  label: string
}

// key, official name, aliases. Aliases are compared after normalising (see `normalise`).
const ICONS: ReadonlyArray<[string, string, string[]]> = [
  ['ec2', 'Amazon EC2', ['ec2', 'elasticcomputecloud']],
  ['ec2-auto-scaling', 'Amazon EC2 Auto Scaling', ['ec2autoscaling', 'autoscaling', 'autoscalinggroup', 'autoscalinggroups', 'asg']],
  ['auto-scaling', 'AWS Auto Scaling', ['applicationautoscaling']],
  ['lambda', 'AWS Lambda', ['lambda', 'lambdafunction', 'lambdafunctions']],
  ['elastic-beanstalk', 'AWS Elastic Beanstalk', ['elasticbeanstalk', 'beanstalk']],
  ['batch', 'AWS Batch', ['batch']],
  ['lightsail', 'Amazon Lightsail', ['lightsail']],
  ['app-runner', 'AWS App Runner', ['apprunner']],
  ['ecs', 'Amazon ECS', ['ecs', 'elasticcontainerservice']],
  ['eks', 'Amazon EKS', ['eks', 'elastickubernetesservice', 'kubernetes']],
  ['fargate', 'AWS Fargate', ['fargate']],
  ['ecr', 'Amazon ECR', ['ecr', 'elasticcontainerregistry']],
  ['vpc', 'Amazon VPC', ['vpc', 'virtualprivatecloud']],
  ['cloudfront', 'Amazon CloudFront', ['cloudfront']],
  ['route-53', 'Amazon Route 53', ['route53']],
  ['api-gateway', 'Amazon API Gateway', ['apigateway', 'apigw']],
  [
    'elastic-load-balancing',
    'Elastic Load Balancing',
    ['elb', 'alb', 'nlb', 'glb', 'elasticloadbalancing', 'elasticloadbalancer', 'applicationloadbalancer', 'networkloadbalancer', 'gatewayloadbalancer', 'loadbalancer'],
  ],
  ['global-accelerator', 'AWS Global Accelerator', ['globalaccelerator']],
  ['direct-connect', 'AWS Direct Connect', ['directconnect']],
  ['transit-gateway', 'AWS Transit Gateway', ['transitgateway', 'tgw']],
  ['privatelink', 'AWS PrivateLink', ['privatelink', 'vpcendpoint', 'vpcendpoints']],
  ['site-to-site-vpn', 'AWS Site-to-Site VPN', ['sitetositevpn', 'vpn']],
  ['client-vpn', 'AWS Client VPN', ['clientvpn']],
  ['cloud-map', 'AWS Cloud Map', ['cloudmap']],
  ['app-mesh', 'AWS App Mesh', ['appmesh']],
  ['vpc-lattice', 'Amazon VPC Lattice', ['vpclattice']],
  ['rds', 'Amazon RDS', ['rds', 'relationaldatabaseservice']],
  ['aurora', 'Amazon Aurora', ['aurora']],
  ['dynamodb', 'Amazon DynamoDB', ['dynamodb', 'dynamo', 'dax', 'dynamodbaccelerator']],
  ['elasticache', 'Amazon ElastiCache', ['elasticache']],
  ['memorydb', 'Amazon MemoryDB', ['memorydb']],
  ['documentdb', 'Amazon DocumentDB', ['documentdb', 'docdb']],
  ['neptune', 'Amazon Neptune', ['neptune']],
  ['keyspaces', 'Amazon Keyspaces', ['keyspaces']],
  ['timestream', 'Amazon Timestream', ['timestream']],
  ['database-migration-service', 'AWS Database Migration Service', ['dms', 'databasemigrationservice']],
  ['redshift', 'Amazon Redshift', ['redshift']],
  ['athena', 'Amazon Athena', ['athena']],
  ['glue', 'AWS Glue', ['glue']],
  ['emr', 'Amazon EMR', ['emr', 'elasticmapreduce']],
  ['opensearch-service', 'Amazon OpenSearch Service', ['opensearch', 'elasticsearch']],
  ['kinesis', 'Amazon Kinesis', ['kinesis']],
  ['kinesis-data-streams', 'Amazon Kinesis Data Streams', ['kinesisdatastreams', 'kinesisstreams']],
  ['data-firehose', 'Amazon Data Firehose', ['datafirehose', 'firehose', 'kinesisdatafirehose', 'kinesisfirehose']],
  ['msk', 'Amazon MSK', ['msk', 'managedstreamingforapachekafka', 'managedstreamingforkafka']],
  ['lake-formation', 'AWS Lake Formation', ['lakeformation']],
  ['sqs', 'Amazon SQS', ['sqs', 'simplequeueservice']],
  ['sns', 'Amazon SNS', ['sns', 'simplenotificationservice']],
  ['eventbridge', 'Amazon EventBridge', ['eventbridge', 'cloudwatchevents']],
  ['step-functions', 'AWS Step Functions', ['stepfunctions', 'stepfunction']],
  ['mq', 'Amazon MQ', ['mq']],
  ['appsync', 'AWS AppSync', ['appsync']],
  ['s3', 'Amazon S3', ['s3', 'simplestorageservice', 's3bucket', 's3buckets', 's3standard', 's3intelligenttiering', 's3static', 's3staticassets', 's3origin']],
  ['s3-glacier', 'Amazon S3 Glacier', ['s3glacier', 'glacier']],
  ['efs', 'Amazon EFS', ['efs', 'elasticfilesystem']],
  ['ebs', 'Amazon EBS', ['ebs', 'elasticblockstore']],
  ['fsx', 'Amazon FSx', ['fsx']],
  ['backup', 'AWS Backup', ['backup']],
  ['storage-gateway', 'AWS Storage Gateway', ['storagegateway']],
  ['elastic-disaster-recovery', 'AWS Elastic Disaster Recovery', ['elasticdisasterrecovery']],
  ['datasync', 'AWS DataSync', ['datasync']],
  ['transfer-family', 'AWS Transfer Family', ['transferfamily']],
  ['iam', 'AWS IAM', ['iam', 'identityandaccessmanagement']],
  ['iam-identity-center', 'AWS IAM Identity Center', ['iamidentitycenter', 'identitycenter']],
  ['kms', 'AWS KMS', ['kms', 'keymanagementservice']],
  ['secrets-manager', 'AWS Secrets Manager', ['secretsmanager']],
  ['waf', 'AWS WAF', ['waf', 'webapplicationfirewall']],
  ['shield', 'AWS Shield', ['shield']],
  ['cognito', 'Amazon Cognito', ['cognito']],
  ['guardduty', 'Amazon GuardDuty', ['guardduty']],
  ['inspector', 'Amazon Inspector', ['inspector']],
  ['macie', 'Amazon Macie', ['macie']],
  ['security-hub', 'AWS Security Hub', ['securityhub']],
  ['certificate-manager', 'AWS Certificate Manager', ['acm', 'certificatemanager']],
  ['network-firewall', 'AWS Network Firewall', ['networkfirewall']],
  ['cloudhsm', 'AWS CloudHSM', ['cloudhsm']],
  ['firewall-manager', 'AWS Firewall Manager', ['firewallmanager']],
  ['detective', 'Amazon Detective', ['detective']],
  ['directory-service', 'AWS Directory Service', ['directoryservice']],
  ['cloudwatch', 'Amazon CloudWatch', ['cloudwatch']],
  ['cloudtrail', 'AWS CloudTrail', ['cloudtrail']],
  ['cloudformation', 'AWS CloudFormation', ['cloudformation']],
  ['systems-manager', 'AWS Systems Manager', ['systemsmanager', 'ssm', 'parameterstore']],
  ['config', 'AWS Config', ['config']],
  ['x-ray', 'AWS X-Ray', ['xray']],
  ['organizations', 'AWS Organizations', ['organizations']],
  ['control-tower', 'AWS Control Tower', ['controltower']],
  ['managed-grafana', 'Amazon Managed Grafana', ['managedgrafana']],
  ['managed-prometheus', 'Amazon Managed Service for Prometheus', ['managedserviceforprometheus', 'managedprometheus']],
  ['trusted-advisor', 'AWS Trusted Advisor', ['trustedadvisor']],
  ['sagemaker', 'Amazon SageMaker AI', ['sagemaker']],
  ['bedrock', 'Amazon Bedrock', ['bedrock']],
  ['rekognition', 'Amazon Rekognition', ['rekognition']],
  ['comprehend', 'Amazon Comprehend', ['comprehend']],
  ['textract', 'Amazon Textract', ['textract']],
  ['transcribe', 'Amazon Transcribe', ['transcribe']],
  ['translate', 'Amazon Translate', ['translate']],
  ['polly', 'Amazon Polly', ['polly']],
  ['lex', 'Amazon Lex', ['lex']],
  ['amplify', 'AWS Amplify', ['amplify']],
  ['location-service', 'Amazon Location Service', ['locationservice']],
  ['ses', 'Amazon SES', ['ses', 'simpleemailservice']],
  ['pinpoint', 'Amazon Pinpoint', ['pinpoint']],
  ['codepipeline', 'AWS CodePipeline', ['codepipeline']],
  ['codebuild', 'AWS CodeBuild', ['codebuild']],
  ['codedeploy', 'AWS CodeDeploy', ['codedeploy']],
  ['mediaconvert', 'AWS Elemental MediaConvert', ['mediaconvert', 'elementalmediaconvert']],
  ['medialive', 'AWS Elemental MediaLive', ['medialive', 'elementalmedialive']],
  ['mediapackage', 'AWS Elemental MediaPackage', ['mediapackage', 'elementalmediapackage']],
  ['interactive-video-service', 'Amazon IVS', ['ivs', 'interactivevideoservice']],
]

/** Every icon key, for checking that each one has a file. */
export const ICON_KEYS: readonly string[] = ICONS.map(([key]) => key)

const VENDOR_WORDS = new Set(['amazon', 'aws'])
// Short aliases ("s3", "mq") only match exactly; longer ones also match the start of a part
// ("aurora" ~ "Aurora PostgreSQL", "cloudwatch" ~ "CloudWatch Logs").
const MIN_PREFIX = 3

/** "Amazon Aurora PostgreSQL" -> "aurorapostgresql": lower case, no vendor words, letters and digits only. */
export function normalise(text: string): string {
  return text
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((word) => word && !VENDOR_WORDS.has(word))
    .join('')
}

/** "Amazon ECS (Fargate) + Auto Scaling" -> ["Amazon ECS", "Fargate", "Auto Scaling"]. */
export function splitServiceName(name: string): string[] {
  return name
    .split(/\s*(?:\+|\/|,|&|\(|\)|\band\b|\bwith\b|\bvia\b)\s*/i)
    .map((part) => part.trim())
    .filter(Boolean)
}

const BY_ALIAS = new Map<string, AwsIcon>()
for (const [key, label, aliases] of ICONS) for (const alias of aliases) BY_ALIAS.set(alias, { key, label })
const PREFIX_ALIASES = [...BY_ALIAS.keys()].filter((alias) => alias.length >= MIN_PREFIX).sort((a, b) => b.length - a.length)

/** The icon for one part of a name, or null when nothing matches confidently. */
export function iconForPart(part: string): AwsIcon | null {
  const key = normalise(part)
  if (!key) return null
  const exact = BY_ALIAS.get(key)
  if (exact) return exact
  const prefix = PREFIX_ALIASES.find((alias) => key.startsWith(alias))
  return prefix ? BY_ALIAS.get(prefix)! : null
}

/** The icons for a whole name, in the order the parts appear, without repeats. */
export function iconsFor(name: string, max = 4): AwsIcon[] {
  const icons: AwsIcon[] = []
  for (const part of splitServiceName(name)) {
    const icon = iconForPart(part)
    if (icon && !icons.some((i) => i.key === icon.key)) icons.push(icon)
    if (icons.length === max) break
  }
  return icons
}
