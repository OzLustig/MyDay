# -*- coding: utf-8 -*- #
# Copyright 2019 Google LLC. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""The register command for registering a clusters with the Hub."""

from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

import textwrap

from apitools.base.py import exceptions as apitools_exceptions
from googlecloudsdk.api_lib.util import exceptions as core_api_exceptions
from googlecloudsdk.calliope import base
from googlecloudsdk.command_lib.container.hub import agent_util as agent_util
from googlecloudsdk.command_lib.container.hub import api_util as api_util
from googlecloudsdk.command_lib.container.hub import exclusivity_util as exclusivity_util
from googlecloudsdk.command_lib.container.hub import kube_util as kube_util
from googlecloudsdk.command_lib.container.hub import util as hub_util
from googlecloudsdk.command_lib.util.apis import arg_utils
from googlecloudsdk.core import exceptions
from googlecloudsdk.core.console import console_io
from googlecloudsdk.core.util import files

SERVICE_ACCOUNT_KEY_FILE_FLAG = '--service-account-key-file'
DOCKER_CREDENTIAL_FILE_FLAG = '--docker-credential-file'


class Register(base.CreateCommand):
  r"""Register a cluster with Hub.

  This command registers a cluster referenced from a kubeconfig file with Hub.
  It creates a membership resource corresponding to this cluster and installs
  the Connect Agent into this cluster. More on the Connect Agent:
  https://cloud.google.com/anthos/multicluster-management/connect/

  If this cluster is previously-registered, then this commands just updates the
  the Connect Agent.

  To authenticate the in-cluster Connect Agent to Google, requires a Google
  Cloud service account key file. Running this command more than once has the
  effect of re-registering the cluster with new parameters but the service
  account key will be preserved if it was provided as part of a previous
  registration.

  ## EXAMPLES

    Register a cluster referenced from the default kubeconfig file, installing
    the Connect Agent:

      $ {command} my-cluster \
        --context=my-cluster-context \
        --service-account-key-file=/tmp/keyfile.json

    Register a cluster referenced from the default kubeconfig file, and
    installing the Connect Agent:

      $ {command} my-cluster \
        --context=my-cluster-context
        --service-account-key-file=/tmp/keyfile.json

    Upgrade the Connect Agent in a cluster:

      $ {command} my-cluster \
        --context=my-cluster-context \
        --service-account-key-file=/tmp/keyfile.json

    Register a GKE cluster using GKE URI, installing the Connect Agent:

      $ {command} my-cluster \
        --gke-uri=my-gke-cluster-uri \
        --service-account-key-file=/tmp/keyfile.json

    Register a GKE cluster by location and name in the same project as the Hub,
    installing the Connect Agent:

      $ {command} my-cluster \
        --gke-cluster=my-gke-cluster-region-or-zone/my-cluster \
        --service-account-key-file=/tmp/keyfile.json

    Register a cluster and output a manifest that can be used to install the
    Connect Agent:

      $ {command} my-cluster \
        --context=my-cluster-context \
        --manifest-output-file=/tmp/manifest.yaml \
        --service-account-key-file=/tmp/keyfile.json

    Register a cluster with a specific version of GKE Connect:

      $ {command} my-cluster \
        --context=my-cluster-context \
        --service-account-key-file=/tmp/keyfile.json \
        --version=gkeconnect_20190802_02_00
  """

  @classmethod
  def Args(cls, parser):
    parser.add_argument(
        'CLUSTER_NAME',
        type=str,
        help=textwrap.dedent("""\
            The name of the cluster being registered. This name is used to
            create a cluster membership in Hub.

         """),
    )
    hub_util.AddUnRegisterCommonArgs(parser)
    parser.add_argument(
        SERVICE_ACCOUNT_KEY_FILE_FLAG,
        type=str,
        required=True,
        help=textwrap.dedent("""\
            The JSON file of a Google Cloud service account private key. This
            service account key is stored as a secret named ``creds-gcp'' in
            gke-connect namespace. To update the ``creds-gcp'' secret in
            gke-connect namespace with a new service account key file, run the
            following command:

            kubectl delete secret creds-gcp -n gke-connect

            kubectl create secret generic creds-gcp -n gke-connect --from-file=creds-gcp.json=/path/to/file
         """),
    )
    parser.add_argument(
        '--manifest-output-file',
        type=str,
        help=textwrap.dedent("""\
            The full path of the file into which the Connect Agent installation
            manifest should be stored. If this option is provided, then the
            manifest will be written to this file and will not be deployed into
            the cluster by gcloud, and it will need to be deployed manually.
          """),
    )
    parser.add_argument(
        '--proxy',
        type=str,
        help=textwrap.dedent("""\
            The proxy address in the format of http[s]://{hostname}. The proxy
            must support the HTTP CONNECT method in order for this connection to
            succeed.
          """),
    )
    parser.add_argument(
        '--version',
        type=str,
        help=textwrap.dedent("""\
          The version of the Connect Agent to install/upgrade if not using the
          latest connect version.
          """),
    )
    parser.add_argument(
        DOCKER_CREDENTIAL_FILE_FLAG,
        type=str,
        hidden=True,
        help=textwrap.dedent("""\
          The credentials to be used if a private registry is provided and auth
          is required. The contents of the file will be stored into a Secret and
          referenced from the imagePullSecrets of the Connect Agent workload.
          """),
    )
    parser.add_argument(
        '--docker-registry',
        type=str,
        hidden=True,
        help=textwrap.dedent("""\
            The registry to pull GKE Connect Agent image if not using
            gcr.io/gkeconnect.
          """),
    )

  def Run(self, args):
    project = arg_utils.GetFromNamespace(args, '--project', use_defaults=True)

    # This incidentally verifies that the kubeconfig and context args are valid.
    kube_client = kube_util.KubernetesClient(args)
    uuid = kube_util.GetClusterUUID(kube_client)
    gke_cluster_self_link = api_util.GKEClusterSelfLink(args)
    # Read the service account files provided in the arguments early, in order
    # to catch invalid files before performing mutating operations.
    try:
      service_account_key_data = hub_util.Base64EncodedFileContents(
          args.service_account_key_file)
    except files.Error as e:
      raise exceptions.Error('Could not process {}: {}'.format(
          SERVICE_ACCOUNT_KEY_FILE_FLAG, e))

    docker_credential_data = None
    if args.docker_credential_file:
      try:
        docker_credential_data = hub_util.Base64EncodedFileContents(
            args.docker_credential_file)
      except files.Error as e:
        raise exceptions.Error('Could not process {}: {}'.format(
            DOCKER_CREDENTIAL_FILE_FLAG, e))

    gke_cluster_self_link = api_util.GKEClusterSelfLink(args)

    # Attempt to create a membership.
    already_exists = False

    obj = None
    # For backward compatiblity, check if a membership was previously created
    # using the cluster uuid.
    parent = api_util.ParentRef(project, 'global')
    membership_id = uuid
    resource_name = api_util.MembershipRef(project, 'global', uuid)
    obj = self._CheckMembershipWithUUID(resource_name, args.CLUSTER_NAME)
    if obj:
      # The membership exists and has the same description.
      already_exists = True
    else:
      # Attempt to create a new membership using cluster_name.
      membership_id = args.CLUSTER_NAME
      resource_name = api_util.MembershipRef(project, 'global',
                                             args.CLUSTER_NAME)
      try:
        self._VerifyClusterExclusivity(kube_client, parent, membership_id)
        obj = api_util.CreateMembership(project, args.CLUSTER_NAME,
                                        args.CLUSTER_NAME,
                                        gke_cluster_self_link, uuid,
                                        self.ReleaseTrack())
      except apitools_exceptions.HttpConflictError as e:
        # If the error is not due to the object already existing, re-raise.
        error = core_api_exceptions.HttpErrorPayload(e)
        if error.status_description != 'ALREADY_EXISTS':
          raise
        # The membership exists with same cluster_name.
        already_exists = True
        obj = api_util.GetMembership(resource_name, self.ReleaseTrack())

    # In case of an existing membership, check with the user to upgrade the
    # Connect-Agent.
    if already_exists:
      console_io.PromptContinue(
          message='A membership for [{}] already exists. Continuing will '
          'reinstall the Connect agent deployment to use a new image (if one '
          'is available).'.format(resource_name),
          cancel_on_no=True)

    # No membership exists. Attempt to create a new one, and install a new
    # agent.
    try:
      self._InstallOrUpdateExclusivityArtifacts(kube_client, resource_name)
      agent_util.DeployConnectAgent(
          args, service_account_key_data, docker_credential_data,
          resource_name, self.ReleaseTrack())
    except:
      # In case of a new membership, we need to clean up membership and
      # resources if we failed to install the Connect Agent.
      if not already_exists:
        api_util.DeleteMembership(resource_name, self.ReleaseTrack())
        exclusivity_util.DeleteMembershipResources(kube_client)
      raise
    return obj

  def _CheckMembershipWithUUID(self, resource_name, cluster_name):
    """Checks for an existing Membership with UUID.

    In the past, by default we used Cluster UUID to create a membership. Now
    we use user supplied cluster_name. This check ensures that we don't
    reregister a cluster.

    Args:
      resource_name: The full membership resource name using the cluster uuid.
      cluster_name: User supplied cluster_name.

    Returns:
     The Membership resource or None.

    Raises:
      exceptions.Error: If it fails to getMembership.
    """
    obj = None
    try:
      obj = api_util.GetMembership(resource_name, self.ReleaseTrack())
      if (hasattr(obj, 'description') and obj.description != cluster_name):
        # A membership exists, but does not have the same cluster_name.
        # This is possible if two different users attempt to register the same
        # cluster, or if the user is upgrading and has passed a different
        # cluster_name. Treat this as an error: even in the upgrade case,
        # this is useful to prevent the user from upgrading the wrong cluster.
        raise exceptions.Error(
            'There is an existing membership, [{}], that conflicts with [{}]. '
            'Please delete it before continuing:\n\n'
            '  gcloud {}container hub memberships delete {}'.format(
                obj.description, cluster_name,
                hub_util.ReleaseTrackCommandPrefix(self.ReleaseTrack()),
                resource_name))
    except apitools_exceptions.HttpNotFoundError:
      # We couldn't find a membership with uuid, so it's safe to create a
      # new one.
      pass
    return obj

  def _VerifyClusterExclusivity(self, kube_client, parent, membership_id):
    """Verifies that the cluster can be registered to the project.

    Args:
      kube_client: a KubernetesClient
      parent: the parent collection the user is attempting to register the
        cluster with.
      membership_id: the ID of the membership to be created for the cluster.

    Raises:
      apitools.base.py.HttpError: if the API request returns an HTTP error.
      exceptions.Error: if the cluster is in an invalid exclusivity state.
    """

    cr_manifest = ''
    # The cluster has been registered.
    if kube_client.MembershipCRDExists():
      cr_manifest = kube_client.GetMembershipCR()

    res = api_util.ValidateExclusivity(cr_manifest, parent,
                                       membership_id,
                                       self.ReleaseTrack())

    if res.status.code:
      raise exceptions.Error(('invalid exclusivity state: {}. If you want ' +
                              'to register the cluster to with {}, please ' +
                              'unregister this cluster first.').format(
                                  parent, res.status.message))

  def _InstallOrUpdateExclusivityArtifacts(self, kube_client, membership_ref):
    """Install the exclusivity artifacts for the cluster.

    Update the exclusivity artifacts if a new version is available if the
    cluster has already being registered.

    Args:
      kube_client: a KubernetesClient
      membership_ref: the full resource name of the membership the cluster is
        registered with.

    Raises:
      apitools.base.py.HttpError: if the API request returns an HTTP error.
      exceptions.Error: if the kubectl interation with the cluster failed.
    """
    crd_manifest = kube_client.GetMembershipCRD()
    cr_manifest = kube_client.GetMembershipCR()
    res = api_util.GenerateExclusivityManifest(crd_manifest,
                                               cr_manifest,
                                               membership_ref)
    kube_client.ApplyMembership(res.crdManifest, res.crManifest)
