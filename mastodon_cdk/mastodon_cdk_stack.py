from aws_cdk import (
    Duration,
    Stack,
    aws_ec2 as ec2,
    aws_certificatemanager as acm,
    aws_route53 as r53,
    aws_rds as rds,
    aws_elasticache as elasticache,
)

from constructs import Construct

class MastodonCdkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(
            self,
            id="mastodon-vpc",
            vpc_name="mastodon-vpc",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=3,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="mastodon-public", 
                    cidr_mask=24,
                    reserved=False, 
                    subnet_type=ec2.SubnetType.PUBLIC
                ),
                ec2.SubnetConfiguration(
                    name="mastodon-private", 
                    cidr_mask=24,
                    reserved=False, 
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
                ),
                ec2.SubnetConfiguration(
                    name="mastodon-db", 
                    cidr_mask=24,
                    reserved=False, 
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                )
            ],
            enable_dns_hostnames=True,
            enable_dns_support=True
        )

        database = rds.DatabaseCluster(
            self, 
            "mastodon-database",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_14_6
            ),
            credentials=rds.Credentials.from_generated_secret("mastodonadmin"),
            instance_props=rds.InstanceProps(
                instance_type=ec2.InstanceType.of(
                    ec2.InstanceClass.BURSTABLE4_GRAVITON, 
                    ec2.InstanceSize.MEDIUM
                ),
                vpc_subnets=ec2.SubnetSelection(
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
                ),
                vpc=vpc,
            )
        )

        mastodon_zone = r53.HostedZone.from_hosted_zone_id(
            self, 
            "mastodon-preexisting-zone", 
            hosted_zone_id="Z08788751CWM32KSLWAVK"
        )

        mastodon_cert = acm.Certificate(
            self,
            "mastodon-certificate",
            domain_name="fails.rip",
            certificate_name="mastodon-failsrip",
            validation=acm.CertificateValidation.from_dns(mastodon_zone)
        )

        mastodon_redis_sg = ec2.SecurityGroup(
            self,
            "mastodon-redis-sg",
            vpc=vpc,
            security_group_name="mastodon-redis-sg",
            allow_all_outbound=True,
        )

        mastodon_redis_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(6379)
        )

        mastodon_redis = elasticache.CfnCacheCluster(
            self, 
            "mastodon-redis-cluster",
            cache_node_type="cache.t4g.micro",
            engine="redis",
            num_cache_nodes=1,
            auto_minor_version_upgrade=True,
            az_mode="single-az",
            # cache_parameter_group_name="cacheParameterGroupName",
            cache_security_group_names=[mastodon_redis_sg.security_group_id],
            # cache_subnet_group_name="cacheSubnetGroupName",
            cluster_name="mastodon-redis-cluster",
            # engine_version="engineVersion",
            # ip_discovery="ipDiscovery",
            # log_delivery_configurations=[elasticache.CfnCacheCluster.LogDeliveryConfigurationRequestProperty(
            #     destination_details=elasticache.CfnCacheCluster.DestinationDetailsProperty(
            #         cloud_watch_logs_details=elasticache.CfnCacheCluster.CloudWatchLogsDestinationDetailsProperty(
            #             log_group="logGroup"
            #         ),
            #         kinesis_firehose_details=elasticache.CfnCacheCluster.KinesisFirehoseDestinationDetailsProperty(
            #             delivery_stream="deliveryStream"
            #         )
            #     ),
            #     destination_type="destinationType",
            #     log_format="logFormat",
            #     log_type="logType"
            # )],
            # network_type="networkType",
            # notification_topic_arn="notificationTopicArn",
            port=6379,
            # preferred_availability_zone="preferredAvailabilityZone",
            # preferred_availability_zones=["preferredAvailabilityZones"],
            # preferred_maintenance_window="preferredMaintenanceWindow",
            # snapshot_arns=["snapshotArns"],
            # snapshot_name="snapshotName",
            # snapshot_retention_limit=123,
            # snapshot_window="snapshotWindow",
            # tags=[CfnTag(
            #     key="key",
            #     value="value"
            # )],
            transit_encryption_enabled=True,
            # vpc_security_group_ids=[mastodon_redis_sg.security_group_id]
        )