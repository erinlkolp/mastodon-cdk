from aws_cdk import (
    Duration,
    Stack,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_ecs_patterns as ecs_patterns,
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
                    ec2.InstanceClass.BURSTABLE2, 
                    ec2.InstanceSize.SMALL
                ),
                vpc_subnets=ec2.SubnetSelection(
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
                ),
                vpc=vpc,
            )
        )