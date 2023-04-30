import os

from aws_cdk import (
    Duration,
    Stack,
    aws_ec2 as ec2,
    aws_certificatemanager as acm,
    aws_route53 as r53,
    aws_rds as rds,
    aws_elasticache as elasticache,
    aws_opensearchservice as es,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_secretsmanager as asm,
)

import json
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

        mastodon_db_secret = asm.Secret(
            self, 
            "mastodon-db-secret",
            generate_secret_string=asm.SecretStringGenerator(
                secret_string_template=json.dumps({"username": "madmin"}),
                generate_string_key="password",
                include_space=False,
                require_each_included_type=True,
                exclude_characters="/@\"",
                exclude_punctuation=True,
            )
        )

        mastodon_db_sg = ec2.SecurityGroup(
            self,
            "mastodon-db-sg",
            vpc=vpc,
            security_group_name="mastodon-db-sg",
            allow_all_outbound=True,
        )

        mastodon_db_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(5432)
        )

        database = rds.DatabaseInstance(
            self, 
            "mastodon-database",
            database_name="bitnami_mastodon",
            multi_az=False,
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_14_7
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE4_GRAVITON, 
                ec2.InstanceSize.SMALL
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            allocated_storage=20,
            auto_minor_version_upgrade=True,
            storage_type=rds.StorageType.GP3,
            security_groups=[mastodon_db_sg],
            credentials=rds.Credentials.from_secret(secret=mastodon_db_secret),
            storage_encrypted=True,
        )

        database.connections.allow_default_port_from_any_ipv4()

        mastodon_zone = r53.HostedZone.from_hosted_zone_id(
            self, 
            "mastodon-preexisting-zone", 
            hosted_zone_id=os.getenv('R53_HOSTED_ZONE')
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

        mastodon_iso_subnet_ids = [ps.subnet_id for ps in vpc.isolated_subnets]

        mastodon_cache_subnet_group = elasticache.CfnSubnetGroup(
            self,
            "mastodon-cache-subnet-group",
            description="mastodon-cache-subnet-group",
            subnet_ids=mastodon_iso_subnet_ids
        )

        mastodon_redis = elasticache.CfnCacheCluster(
            self,
            "mastodon-redis-cluster",
            engine="redis", # "redis" or "memcached"
            cache_node_type="cache.t4g.micro",
            num_cache_nodes=1,
            engine_version="7.0",
            port=6379,
            auto_minor_version_upgrade=True,
            az_mode="single-az",
            cache_subnet_group_name=mastodon_cache_subnet_group.ref,
            vpc_security_group_ids=[mastodon_redis_sg.security_group_id],
        )

        # ECS Cluster Configuration
        mastodon_cluster = ecs.Cluster(
            self,
            "mastodon-ecs-cluster",
            vpc=vpc,
            cluster_name="mastodon-ecs-cluster",
            enable_fargate_capacity_providers=True,
            container_insights=True,
        )

        mastodon_admin_secret = asm.Secret(
            self, 
            "mastodon-admin-secret",
            generate_secret_string=asm.SecretStringGenerator(
                secret_string_template=json.dumps({"username": "madmin"}),
                generate_string_key="password",
                include_space=False,
                require_each_included_type=True
            )
        )

        mastodon_web_sg = ec2.SecurityGroup(
            self,
            "mastodon-web-sg",
            vpc=vpc,
            security_group_name="mastodon-web-sg",
            allow_all_outbound=True,
        )

        mastodon_web_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(8080)
        )

        mastodon_web_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(3000)
        )

        mastodon_web_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(80)
        )

        mastodon_priv_subnet_ids = [ps.subnet_id for ps in vpc.private_subnets]

        mastodon_web_container = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, 
            "mastodon-web-container",
            cluster=mastodon_cluster,
            assign_public_ip=False,
            certificate=mastodon_cert,
            desired_count=1,
            cpu=512,
            public_load_balancer=True,
            memory_limit_mib=1024,
            load_balancer_name="mastodon-lb-web",
            listener_port=443,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_registry("docker.io/bitnami/mastodon:latest"),
                container_port=3000,
                enable_logging=True,
                secrets={
                    "MASTODON_ADMIN_USERNAME": ecs.Secret.from_secrets_manager(mastodon_admin_secret, "username"),
                    "MASTODON_ADMIN_PASSWORD": ecs.Secret.from_secrets_manager(mastodon_admin_secret, "password"),
                    "MASTODON_DATABASE_PASSWORD": ecs.Secret.from_secrets_manager(mastodon_db_secret, "password")
                },
                environment={
                    "ALLOW_EMPTY_PASSWORD": "yes",
                    "MASTODON_MODE": "web",
                    "MASTODON_DATABASE_HOST": str(database.db_instance_endpoint_address),
                    "MASTODON_DATABASE_USER": str(mastodon_db_secret.secret_value_from_json("username")),
                    "MASTODON_REDIS_HOST": str(mastodon_redis.attr_redis_endpoint_address)
                },
            ),
            task_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[mastodon_web_sg]
        )
