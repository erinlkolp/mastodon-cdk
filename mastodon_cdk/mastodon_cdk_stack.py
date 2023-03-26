from aws_cdk import (
    Duration,
    Stack,
    aws_ec2 as ec2,
    aws_certificatemanager as acm,
    aws_route53 as r53,
    aws_rds as rds,
    aws_elasticache as elasticache,
    aws_opensearchservice as es,
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

        # TRASH - Please take out. -elk 3/25/2023
        # mastodon_cache_sg = elasticache.CfnSecurityGroup(
        #     self,
        #     "mastodon-cache-sg",
        #     description="mastodon-cache-sg"
        # )

        mastodon_priv_subnet_ids = [ps.subnet_id for ps in vpc.private_subnets]

        mastodon_cache_subnet_group = elasticache.CfnSubnetGroup(
            self,
            "mastodon-cache-subnet-group",
            description="mastodon-cache-subnet-group",
            subnet_ids=mastodon_priv_subnet_ids
        )

        mastodon_redis = elasticache.CfnCacheCluster(
            self,
            "mastodon-redis-cluster",
            engine="redis",
            cache_node_type="cache.t4g.micro",
            num_cache_nodes=1,
            engine_version="7.0",
            port=6379,
            auto_minor_version_upgrade=True,
            az_mode="single-az",
            # cache_subnet_group_name=mastodon_cache_subnet_group.cache_subnet_group_name, # This does not appear to work. FIX THIS. -elk 3/25/2023
            cache_subnet_group_name="mastodoncdkstack-mastodoncachesubnetgroup-5zr9eb4bjukv",
            vpc_security_group_ids=[mastodon_redis_sg.security_group_id],
        )

