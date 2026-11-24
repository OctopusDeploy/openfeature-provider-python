from dataclasses import KW_ONLY, dataclass, field
from datetime import timedelta

import httpx

from octopus_openfeature_provider._product_metadata import ProductMetadata

_DEFAULT_SERVER_URL = "https://features.octopus.com"


@dataclass
class OctopusFeatureConfiguration:
    """Configures an `OctopusFeatureProvider`.

    The provider takes its own copy when it's built, so later changes to a
    configuration don't affect a provider that's already been built.

    Attributes:
        client_identifier: The value of the Octopus variable
            `Octopus.FeatureFlags.ClientIdentifier`.
        product_metadata: Describes the product using the provider.
        cache_duration: How often the provider polls the feature flags service
            for new feature flag evaluations. Must be positive.
        request_timeout: How long each phase of a request to the feature
            flags service may take before it's abandoned: connecting, waiting
            for a pooled connection, sending the request, and each read of
            the response. It doesn't limit a request's total time. If
            `http_client` has its own timeouts, the shorter limit applies to
            each phase. Keep it well under `cache_duration` so a stalled
            request can't hold up the next poll. Must be positive. Shutting the
            provider down waits for a request in flight.
        release_version_override: Overrides the application release version
            embedded in `client_identifier`. It's sent to the feature flags
            service only when it isn't `None`.
        http_client: Used for requests to the feature flags service, for
            example to configure a proxy, TLS or instrumentation. `None` means
            the provider creates and owns its own client. The provider never
            closes a client supplied here.
    """

    client_identifier: str
    product_metadata: ProductMetadata
    _: KW_ONLY
    cache_duration: timedelta = timedelta(minutes=1)
    request_timeout: timedelta = timedelta(seconds=10)
    release_version_override: str | None = None
    http_client: httpx.Client | None = None

    # Only tests override this. Customers always use the default.
    _server_url: str = field(default=_DEFAULT_SERVER_URL, init=False, repr=False)
