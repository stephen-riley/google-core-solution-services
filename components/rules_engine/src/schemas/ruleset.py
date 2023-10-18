# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pydantic Model for RuleSet API's"""

from pydantic import BaseModel

class RulesetFieldsSchema(BaseModel):
  """Ruleset Fields Pydantic Model"""

  # This is the reference API spec for Rule data model.
  fields: dict = {}

  class Config:
    orm_mode = True
    schema_extra = {
      "example": {
        "fields": {
          "field-1": "str",
          "field-2": "int",
        }
      }
    }
