from gettext import gettext as _

from django.conf import settings
from django.core import validators
from django.db.models import Q

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from pulpcore.plugin import serializers as platform
from pulpcore.plugin.models import Artifact, Publication, Repository

from . import models


class MinimalArtifactSerializer(platform.ArtifactSerializer):
    """
    Serialize Artifacts associated with Docker Content.

    We overrided the platform serializer because it does not include size, and includes digest.
    Since digest is a field on the content units, it would be redundant.
    """

    class Meta:
        fields = ('size', '_href')
        model = Artifact


class ManifestListTagSerializer(platform.ContentSerializer):
    """
    Serializer for ManifestListTags.
    """

    name = serializers.CharField(help_text="Tag name")
    manifest_list = platform.DetailRelatedField(
        many=False,
        help_text="Manifest List that is tagged",
        view_name='docker-manifest-lists-detail',
        queryset=models.ManifestList.objects.all()
    )
    _artifact = MinimalArtifactSerializer(many=False, help_text="File related to this content")

    class Meta:
        fields = tuple(
            set(platform.ContentSerializer.Meta.fields) - {'_artifacts'}
        ) + ('name', 'manifest_list', '_artifact')
        model = models.ManifestListTag


class ManifestTagSerializer(platform.ContentSerializer):
    """
    Serializer for ManifestTags.
    """

    name = serializers.CharField(help_text="Tag name")
    manifest = platform.DetailRelatedField(
        many=False,
        help_text="Manifest that is tagged",
        view_name='docker-manifests-detail',
        queryset=models.ImageManifest.objects.all()
    )
    _artifact = MinimalArtifactSerializer(many=False, help_text="File related to this content")

    class Meta:
        fields = tuple(
            set(platform.ContentSerializer.Meta.fields) - {'_artifacts'}
        ) + ('name', 'manifest', '_artifact')
        model = models.ManifestTag


class ManifestListSerializer(platform.ContentSerializer):
    """
    Serializer for ManifestLists.
    """

    digest = serializers.CharField(help_text="sha256 of the ManifestList file")
    schema_version = serializers.IntegerField(help_text="Docker schema version")
    media_type = serializers.CharField(help_text="Docker media type of the file")
    manifests = platform.DetailRelatedField(
        many=True,
        help_text="Manifests that are referenced by this Manifest List",
        view_name='docker-manifests-detail',
        queryset=models.ImageManifest.objects.all()
    )
    _artifact = MinimalArtifactSerializer(many=False, help_text="File related to this content")

    class Meta:
        fields = tuple(
            set(platform.ContentSerializer.Meta.fields) - {'_artifacts'}
        ) + ('digest', 'schema_version', 'media_type', 'manifests', '_artifact')
        model = models.ManifestList


class ManifestSerializer(platform.ContentSerializer):
    """
    Serializer for Manifests.
    """

    digest = serializers.CharField(help_text="sha256 of the Manifest file")
    schema_version = serializers.IntegerField(help_text="Docker schema version")
    media_type = serializers.CharField(help_text="Docker media type of the file")
    blobs = platform.DetailRelatedField(
        many=True,
        help_text="Blobs that are referenced by this Manifest",
        view_name='docker-blobs-detail',
        queryset=models.ManifestBlob.objects.all()
    )
    config_blob = platform.DetailRelatedField(
        many=False,
        help_text="Blob that contains configuration for this Manifest",
        view_name='docker-blobs-detail',
        queryset=models.ManifestBlob.objects.all()
    )
    _artifact = MinimalArtifactSerializer(many=False, help_text="File related to this content")

    class Meta:
        fields = tuple(
            set(platform.ContentSerializer.Meta.fields) - {'_artifacts'}
        ) + ('digest', 'schema_version', 'media_type', 'blobs', 'config_blob', '_artifact')
        model = models.ImageManifest


class BlobSerializer(platform.ContentSerializer):
    """
    Serializer for Blobs.
    """

    digest = serializers.CharField(help_text="sha256 of the Blob file")
    media_type = serializers.CharField(help_text="Docker media type of the file")
    _artifact = MinimalArtifactSerializer(many=False, help_text="File related to this content")

    class Meta:
        fields = tuple(
            set(platform.ContentSerializer.Meta.fields) - {'_artifacts'}
        ) + ('digest', 'media_type', '_artifact')
        model = models.ManifestBlob


class RegistryPathField(serializers.CharField):
    """
    Serializer Field for the registry_path field of the DockerDistribution.
    """

    def to_representation(self, value):
        """
        Converts a base_path into a registry path.
        """
        if settings.CONTENT_HOST:
            host = settings.CONTENT_HOST
        else:
            host = self.context['request'].get_host()
        return ''.join([host, '/', value])


class DockerRemoteSerializer(platform.RemoteSerializer):
    """
    A Serializer for DockerRemote.

    Add any new fields if defined on DockerRemote.
    Similar to the example above, in DockerContentSerializer.
    Additional validators can be added to the parent validators list

    For example::

    class Meta:
        validators = platform.RemoteSerializer.Meta.validators + [myValidator1, myValidator2]
    """

    upstream_name = serializers.CharField(
        required=True,
        allow_blank=False,
        help_text=_("Name of the upstream repository")
    )

    class Meta:
        fields = platform.RemoteSerializer.Meta.fields + ('upstream_name',)
        model = models.DockerRemote


class DockerPublisherSerializer(platform.PublisherSerializer):
    """
    A Serializer for DockerPublisher.

    Add any new fields if defined on DockerPublisher.
    Similar to the example above, in DockerContentSerializer.
    Additional validators can be added to the parent validators list

    For example::

    class Meta:
        validators = platform.PublisherSerializer.Meta.validators + [myValidator1, myValidator2]
    """

    class Meta:
        fields = platform.PublisherSerializer.Meta.fields
        model = models.DockerPublisher


class DockerDistributionSerializer(platform.ModelSerializer):
    """
    A serializer for DockerDistribution.
    """

    _href = platform.IdentityField(
        view_name='docker-distributions-detail'
    )
    name = serializers.CharField(
        help_text=_('A unique distribution name. Ex, `rawhide` and `stable`.'),
        validators=[validators.MaxLengthValidator(
            models.DockerDistribution._meta.get_field('name').max_length,
            message=_('Distribution name length must be less than {} characters').format(
                models.DockerDistribution._meta.get_field('name').max_length
            )),
            UniqueValidator(queryset=models.DockerDistribution.objects.all())]
    )
    base_path = serializers.CharField(
        help_text=_('The base (relative) path component of the published url. Avoid paths that \
                    overlap with other distribution base paths (e.g. "foo" and "foo/bar")'),
        validators=[validators.MaxLengthValidator(
            models.DockerDistribution._meta.get_field('base_path').max_length,
            message=_('Distribution base_path length must be less than {} characters').format(
                models.DockerDistribution._meta.get_field('base_path').max_length
            )),
            UniqueValidator(queryset=models.DockerDistribution.objects.all()),
        ]
    )
    publisher = platform.DetailRelatedField(
        required=False,
        help_text=_('Publications created by this publisher and repository are automatically'
                    'served as defined by this distribution'),
        queryset=models.DockerPublisher.objects.all(),
        allow_null=True
    )
    publication = platform.RelatedField(
        required=False,
        help_text=_('The publication being served as defined by this distribution'),
        queryset=Publication.objects.exclude(complete=False),
        view_name='publications-detail',
        allow_null=True
    )
    repository = platform.RelatedField(
        required=False,
        help_text=_('Publications created by this repository and publisher are automatically'
                    'served as defined by this distribution'),
        queryset=Repository.objects.all(),
        view_name='repositories-detail',
        allow_null=True
    )
    registry_path = RegistryPathField(
        source='base_path', read_only=True,
        help_text=_('The Registry hostame:port/name/ to use with docker pull command defined by '
                    'this distribution.')
    )

    class Meta:
        model = models.DockerDistribution
        fields = platform.ModelSerializer.Meta.fields + (
            'name',
            'base_path',
            'publisher',
            'publication',
            'registry_path',
            'repository',
            'content_guard',
        )

    def _validate_path_overlap(self, path):
        # look for any base paths nested in path
        search = path.split("/")[0]
        q = Q(base_path=search)
        for subdir in path.split("/")[1:]:
            search = "/".join((search, subdir))
            q |= Q(base_path=search)

        # look for any base paths that nest path
        q |= Q(base_path__startswith='{}/'.format(path))
        qs = models.DockerDistribution.objects.filter(q)

        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)

        match = qs.first()
        if match:
            raise serializers.ValidationError(detail=_("Overlaps with existing distribution '"
                                                       "{}'").format(match.name))

        return path

    def validate_base_path(self, path):
        """
        Validate that path is valid.

        Args:
            path (str): the path at which the registry will be served at
        """
        self._validate_relative_path(path)
        return self._validate_path_overlap(path)

    def validate(self, data):
        """
        Validates that the data dict has valid DockerDistribution info.

        Args:
            data (dict): dict representing a DockerDistribution
        """
        super().validate(data)

        if 'publisher' in data:
            publisher = data['publisher']
        elif self.instance:
            publisher = self.instance.publisher
        else:
            publisher = None

        if 'repository' in data:
            repository = data['repository']
        elif self.instance:
            repository = self.instance.repository
        else:
            repository = None

        if publisher and not repository:
            raise serializers.ValidationError({'repository': _("Repository must be set if "
                                                               "publisher is set.")})
        if repository and not publisher:
            raise serializers.ValidationError({'publisher': _("Publisher must be set if "
                                                              "repository is set.")})

        return data
