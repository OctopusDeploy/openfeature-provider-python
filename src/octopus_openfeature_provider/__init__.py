"""The Octopus Deploy OpenFeature provider."""

import logging

from octopus_openfeature_provider._configuration import OctopusFeatureConfiguration
from octopus_openfeature_provider._product_metadata import ProductMetadata
from octopus_openfeature_provider._provider import OctopusFeatureProvider
from octopus_openfeature_provider._version import __version__

# Silent unless the application configures logging for this package.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "OctopusFeatureConfiguration",
    "OctopusFeatureProvider",
    "ProductMetadata",
    "__version__",
]
