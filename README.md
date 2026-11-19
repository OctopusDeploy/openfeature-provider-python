# Octopus Deploy OpenFeature provider for Python

[![PyPI](https://img.shields.io/pypi/v/octopus-openfeature-provider)](https://pypi.org/project/octopus-openfeature-provider/)
[![CI build](https://github.com/OctopusDeploy/openfeature-provider-python/actions/workflows/main.yml/badge.svg?branch=main)](https://github.com/OctopusDeploy/openfeature-provider-python/actions/workflows/main.yml?query=branch:main)

The Octopus Deploy Python [OpenFeature provider](https://openfeature.dev/docs/reference/concepts/provider/), to be used with the [OpenFeature Python SDK](https://openfeature.dev/docs/reference/technologies/server/python/). It evaluates [Octopus feature flags](https://octopus.com/docs/feature-flags) in your Python application.

The provider is for server-side applications, such as web services, workers and command-line tools. It isn't intended for clients such as desktop applications.

> **Note:** This provider is under active development and isn't ready for use yet. The API may change without notice until the first release.

## Supported Python versions

The provider supports Python 3.11 and later. It's tested on every maintained CPython version.

## Installation

```bash
pip install octopus-openfeature-provider
```

This also installs the [OpenFeature SDK](https://pypi.org/project/openfeature-sdk/) (`openfeature-sdk`), which your application uses to evaluate flags.

## Usage

```python
from openfeature import api
from openfeature.evaluation_context import EvaluationContext

from octopus_openfeature_provider import (
    OctopusFeatureConfiguration,
    OctopusFeatureProvider,
    ProductMetadata,
)

provider = OctopusFeatureProvider(
    OctopusFeatureConfiguration(
        client_identifier="YourClientIdentifier",
        product_metadata=ProductMetadata("YourProductName", "1.0.0"),
    )
)

# Wait for the provider at startup, so your first evaluations don't get the default value.
api.set_provider_and_wait(provider)

client = api.get_client()

# Evaluation context is passed with each evaluation, so one provider serves every request.
context = EvaluationContext(attributes={"userid": "bob@octopus.com"})
if client.get_boolean_value("to-the-moon-feature", False, context):
    print("🚀🚀🚀")
```

Octopus feature flags are boolean, so evaluate them with `get_boolean_value` or `get_boolean_details`. Evaluating a flag as a string, integer, float or object returns your default value with an error code.

Call `api.shutdown()` when your application stops, so the provider releases its resources.

For more on evaluating flags, see the [OpenFeature evaluation API documentation](https://openfeature.dev/docs/reference/concepts/evaluation-api/).

## Configuration

`OctopusFeatureConfiguration` takes these arguments. Pass everything after `product_metadata` by keyword.

| Argument | Required | Description |
| --- | --- | --- |
| `client_identifier` | Yes | The client identifier from the Octopus variable `Octopus.FeatureFlags.ClientIdentifier`. |
| `product_metadata` | Yes | A `ProductMetadata` with the name and, optionally, version of your application, sent to Octopus for telemetry. |
| `cache_duration` | No | A `timedelta` for how often the provider checks for changed flags. Defaults to one minute. Must be positive. |
| `request_timeout` | No | A `timedelta` for how long a request to Octopus may take in total before it's abandoned. Defaults to 10 seconds. Must be positive. |
| `release_version_override` | No | Overrides the release version embedded in the client identifier. |
| `http_client` | No | An `httpx.Client` for requests to Octopus, for example to configure a proxy, TLS or instrumentation. The provider never closes a client you supply. By default, it creates and manages its own. |

The provider takes a copy of the configuration when it's created, so later changes to the configuration don't affect it. It raises `ValueError` or `TypeError` if the configuration isn't valid.

### Logging

The provider logs through the standard `logging` module, under the `octopus_openfeature_provider` logger. It's silent unless your application configures logging.

## About Octopus Deploy

[Octopus Deploy](https://octopus.com) is a sophisticated, best-of-breed continuous delivery (CD) platform for modern software teams. Octopus offers powerful release orchestration, deployment automation, and runbook automation, while handling the scale, complexity and governance expectations of even the largest organizations with the most complex deployment challenges.

## Contributing

See [CONTRIBUTING.md](https://github.com/OctopusDeploy/openfeature-provider-python/blob/main/CONTRIBUTING.md) to build and test locally.

## License

[Apache 2.0](https://github.com/OctopusDeploy/openfeature-provider-python/blob/main/LICENSE)
