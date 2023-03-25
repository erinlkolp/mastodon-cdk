import aws_cdk as core
import aws_cdk.assertions as assertions

from mastodon_cdk.mastodon_cdk_stack import MastodonCdkStack

# example tests. To run these tests, uncomment this file along with the example
# resource in mastodon_cdk/mastodon_cdk_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = MastodonCdkStack(app, "mastodon-cdk")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
