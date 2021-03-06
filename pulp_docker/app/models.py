from logging import getLogger
from types import SimpleNamespace

from django.db import models

from pulpcore.plugin.download import DownloaderFactory
from pulpcore.plugin.models import BaseDistribution, Content, Remote, Publisher

from . import downloaders


logger = getLogger(__name__)


MEDIA_TYPE = SimpleNamespace(
    MANIFEST_V1='application/vnd.docker.distribution.manifest.v1+json',
    MANIFEST_V2='application/vnd.docker.distribution.manifest.v2+json',
    MANIFEST_LIST='application/vnd.docker.distribution.manifest.list.v2+json',
    CONFIG_BLOB='application/vnd.docker.container.image.v1+json',
    REGULAR_BLOB='application/vnd.docker.image.rootfs.diff.tar.gzip',
    FOREIGN_BLOB='application/vnd.docker.image.rootfs.foreign.diff.tar.gzip',
)


class SingleArtifact:
    """
    Mixin for Content with only 1 artifact.
    """

    @property
    def _artifact(self):
        """
        Return the artifact (there is only one for this content type).
        """
        return self._artifacts.get()


class ManifestBlob(Content, SingleArtifact):
    """
    A blob defined within a manifest.

    The actual blob file is stored as an artifact.

    Fields:
        digest (models.CharField): The blob digest.
        media_type (models.CharField): The blob media type.

    Relations:
        manifest (models.ForeignKey): Many-to-one relationship with Manifest.
    """

    TYPE = 'manifest-blob'

    digest = models.CharField(max_length=255)
    media_type = models.CharField(
        max_length=80,
        choices=(
            (MEDIA_TYPE.CONFIG_BLOB, MEDIA_TYPE.CONFIG_BLOB),
            (MEDIA_TYPE.REGULAR_BLOB, MEDIA_TYPE.REGULAR_BLOB),
            (MEDIA_TYPE.FOREIGN_BLOB, MEDIA_TYPE.FOREIGN_BLOB),
        ))

    class Meta:
        unique_together = ('digest',)


class ImageManifest(Content, SingleArtifact):
    """
    A docker manifest.

    This content has one artifact.

    Fields:
        digest (models.CharField): The manifest digest.
        schema_version (models.IntegerField): The docker schema version.
        media_type (models.CharField): The manifest media type.
    """

    TYPE = 'manifest'

    digest = models.CharField(max_length=255)
    schema_version = models.IntegerField()
    media_type = models.CharField(
        max_length=60,
        choices=(
            (MEDIA_TYPE.MANIFEST_V1, MEDIA_TYPE.MANIFEST_V1),
            (MEDIA_TYPE.MANIFEST_V2, MEDIA_TYPE.MANIFEST_V2),
        ))

    blobs = models.ManyToManyField(ManifestBlob, through='BlobManifestBlob')
    config_blob = models.ForeignKey(ManifestBlob, related_name='config_blob',
                                    null=True, on_delete=models.CASCADE)  # through table?

    class Meta:
        unique_together = ('digest',)


class ManifestList(Content, SingleArtifact):
    """
    A manifest list.

    This content has one artifact.

    Fields:
        digest (models.CharField): The manifest digest.
        schema_version (models.IntegerField): The docker schema version.
        media_type (models.CharField): The manifest media type.

    Relations:
        manifests (models.ManyToManyField): Many-to-many relationship with Manifest.
    """

    TYPE = 'manifest-list'

    digest = models.CharField(max_length=255)
    schema_version = models.IntegerField()
    media_type = models.CharField(
        max_length=60,
        choices=(
            (MEDIA_TYPE.MANIFEST_LIST, MEDIA_TYPE.MANIFEST_LIST),
        ))

    manifests = models.ManyToManyField(ImageManifest, through='ManifestListManifest')

    class Meta:
        unique_together = ('digest',)


class BlobManifestBlob(models.Model):
    """
    Many-to-many relationship between ManifestBlobs and ImageManifests.
    """

    manifest = models.ForeignKey(
        ImageManifest, related_name='blob_manifests', on_delete=models.CASCADE)
    manifest_blob = models.ForeignKey(
        ManifestBlob, related_name='manifest_blobs', on_delete=models.CASCADE)

    class Meta:
        unique_together = ('manifest', 'manifest_blob')


class ManifestListManifest(models.Model):
    """
    The manifest referenced by a manifest list.

    Fields:
        architecture (models.CharField): The platform architecture.
        variant (models.CharField): The platform variant.
        features (models.TextField): The platform features.
        os (models.CharField): The platform OS name.
        os_version (models.CharField): The platform OS version.
        os_features (models.TextField): The platform OS features.

    Relations:
        manifest (models.ForeignKey): Many-to-one relationship with Manifest.
        manifest_list (models.ForeignKey): Many-to-one relationship with ManifestList.
    """

    architecture = models.CharField(max_length=255)
    os = models.CharField(max_length=255)
    os_version = models.CharField(max_length=255)
    os_features = models.TextField(default='', blank=True)
    features = models.TextField(default='', blank=True)
    variant = models.CharField(max_length=255)

    manifest = models.ForeignKey(
        ImageManifest, related_name='manifests', on_delete=models.CASCADE)
    manifest_list = models.ForeignKey(
        ManifestList, related_name='manifest_lists', on_delete=models.CASCADE)

    class Meta:
        unique_together = ('manifest', 'manifest_list')


class ManifestTag(Content, SingleArtifact):
    """
    A tagged Manifest.

    Fields:
        name (models.CharField): The tag name.

    Relations:
        manifest (models.ForeignKey): A referenced Manifest.

    """

    TYPE = 'manifest-tag'

    name = models.CharField(max_length=255, db_index=True)

    manifest = models.ForeignKey(
        ImageManifest, null=True, related_name='manifest_tags', on_delete=models.CASCADE)

    class Meta:
        unique_together = (
            ('name', 'manifest'),
        )


class ManifestListTag(Content, SingleArtifact):
    """
    A tagged Manifest List.

    Fields:
        name (models.CharField): The tag name.

    Relations:
        manifest_list (models.ForeignKey): A referenced Manifest List.

    """

    TYPE = 'manifest-list-tag'

    name = models.CharField(max_length=255, db_index=True)

    manifest_list = models.ForeignKey(
        ManifestList, null=True, related_name='manifest_list_tags', on_delete=models.CASCADE)

    class Meta:
        unique_together = (
            ('name', 'manifest_list'),
        )


class DockerPublisher(Publisher):
    """
    A Publisher for DockerContent.

    Define any additional fields for your new publisher if needed.
    """

    TYPE = 'docker'


class DockerRemote(Remote):
    """
    A Remote for DockerContent.
    """

    upstream_name = models.CharField(max_length=255, db_index=True)

    TYPE = 'docker'

    @property
    def download_factory(self):
        """
        Return the DownloaderFactory which can be used to generate asyncio capable downloaders.

        Upon first access, the DownloaderFactory is instantiated and saved internally.

        Plugin writers are expected to override when additional configuration of the
        DownloaderFactory is needed.

        Returns:
            DownloadFactory: The instantiated DownloaderFactory to be used by
                get_downloader()

        """
        try:
            return self._download_factory
        except AttributeError:
            self._download_factory = DownloaderFactory(
                self,
                downloader_overrides={
                    'http': downloaders.TokenAuthHttpDownloader,
                    'https': downloaders.TokenAuthHttpDownloader,
                }
            )
            return self._download_factory

    def get_downloader(self, url, **kwargs):
        """
        Get a downloader for this url.

        Args:
            url (str): URL to fetch from.

        Returns:
            subclass of :class:`~pulpcore.plugin.download.BaseDownloader`: A downloader that
            is configured with the remote settings.

        """
        kwargs['remote'] = self
        return self.download_factory.build(url, **kwargs)

    @property
    def namespaced_upstream_name(self):
        """
        Returns an upstream Docker repository name with a namespace.

        For upstream repositories that do not have a namespace, the convention is to use 'library'
        as the namespace.
        """
        # TODO File issue: only for dockerhub??? This doesn't work against a Pulp2+crane repo
        if '/' not in self.upstream_name:
            return 'library/{name}'.format(name=self.upstream_name)
        else:
            return self.upstream_name


class DockerDistribution(BaseDistribution):
    """
    A docker distribution defines how a publication is distributed by Pulp's webserver.
    """

    class Meta:
        default_related_name = 'docker_distributions'
