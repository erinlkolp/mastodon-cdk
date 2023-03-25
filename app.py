#!/usr/bin/env python3
import os

import aws_cdk as cdk

from mastodon_cdk.mastodon_cdk_stack import MastodonCdkStack


app = cdk.App()

MastodonCdkStack(
    app, 
    "MastodonCdkStack",
    env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),    
)

app.synth()
