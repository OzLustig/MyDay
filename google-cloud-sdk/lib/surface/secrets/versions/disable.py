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
"""Disable the version of the provided secret."""

from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

from googlecloudsdk.api_lib.secrets import api as secrets_api
from googlecloudsdk.calliope import base
from googlecloudsdk.command_lib.secrets import args as secrets_args
from googlecloudsdk.command_lib.secrets import log as secrets_log
from googlecloudsdk.command_lib.secrets import util as secrets_util


class Create(base.DeleteCommand):
  r"""Disable the version of the provided secret.

  Disable the version of the provided secret. It can be re-enabled with
  `{parent_command} enable`.

  ## EXAMPLES

  Disable version '123' of the secret named 'my-secret':

    $ {command} 123 --secret=my-secret
  """

  @staticmethod
  def Args(parser):
    secrets_args.AddVersion(
        parser, purpose='to disable', positional=True, required=True)

  def Run(self, args):
    version_ref = args.CONCEPTS.version.Parse()
    result = secrets_api.Versions(
        version=secrets_util.GetVersionFromReleasePath(
            self.ReleaseTrack())).Disable(version_ref)
    secrets_log.Versions().Disabled(version_ref)
    return result
