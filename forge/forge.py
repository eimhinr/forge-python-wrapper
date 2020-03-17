from __future__ import absolute_import

import os
import time

from tqdm import tqdm

from .api import ForgeApi
from .auth import ForgeAuth
from .base import ForgeBase, Logger

logger = Logger.start(__name__)


class ForgeApp(ForgeBase):
    def __init__(
        self,
        client_id=None,
        client_secret=None,
        scopes=None,
        hub_id=None,
        three_legged=False,
        grant_type="implicit",
        redirect_uri=None,
        username=None,
        password=None,
        log_level="info",
    ):
        """
        """
        self.auth = ForgeAuth(
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes,
            redirect_uri=redirect_uri,
            three_legged=three_legged,
            grant_type=grant_type,
            username=username,
            password=password,
            log_level=log_level,
        )

        self.api = ForgeApi(auth=self.auth, log_level=log_level)

        if hub_id or os.environ.get("FORGE_HUB_ID"):
            self.hub_id = hub_id or os.environ.get("FORGE_HUB_ID")

        self.logger = logger
        Logger.set_level(self.logger, log_level)

    def __repr__(self):
        return "<Forge App - Hub ID: {} at {}>".format(
            self.hub_id, hex(id(self))
        )

    def _validate_hub(func):
        def inner(self, *args, **kwargs):
            if not self.hub_id:
                raise AttributeError("A 'app.hub_id' has not been defined.")
            return func(self, *args, **kwargs)

        return inner

    def _validate_bim360_hub(func):
        def inner(self, *args, **kwargs):
            if self.auth.three_legged:
                raise ValueError(
                    "The BIM 360 API only supports 2-legged access token."
                )
            elif not self.hub_id:
                raise AttributeError("A 'app.hub_id' has not been defined.")
            elif self.hub_id[:2] != "b.":
                raise ValueError(
                    "The 'app.hub_id' must be a {} hub.".format(
                        ForgeBase.NAMESPACES["b."]
                    )
                )
            return func(self, *args, **kwargs)

        return inner

    @property
    def hub_id(self):
        if getattr(self, "_hub_id", None):
            return self._hub_id

    @hub_id.setter
    def hub_id(self, val):
        self._set_hub_id(val)
        self.api.dm.hub_id = val
        self.api.hq.hub_id = val

    def get_hubs(self):
        self.hubs = self.api.dm.get_hubs().get("data")

    @_validate_hub
    def get_projects(self, source="all"):
        """
        Get all projects and sets the self.projects attribute
        Kwargs:
            source (``string``, default="all"): "all", "admin" or "docs"
        Returns:
            {
                id_1: {"docs": {}, "admin": {}},
                id_2: {"docs": {}, "admin": {}},
                id_3: {"docs": {}, "admin": {}},
                id_4: {"admin": {}},
                ...
            }
        """
        self.projects = []
        self._project_indices_by_id = {}
        self._project_indices_by_name = {}

        if self.hub_type == self.NAMESPACES["a."]:
            if not self.auth.three_legged:
                self.logger.warning(
                    "Failed to get projects. '{}' hubs only supports 3-legged access token.".format(  # noqa:E501
                        self.NAMESPACES["a."]
                    )
                )
            else:
                for project in self.api.dm.get_projects():
                    self.projects.append(
                        Project(
                            project["attributes"]["name"],
                            project["id"][2:],
                            data=project,
                            app=self,
                        )
                    )

                    self._project_indices_by_id[project["id"][2:]] = (
                        len(self.projects) - 1
                    )
                    self._project_indices_by_name[
                        project["attributes"]["name"]
                    ] = (len(self.projects) - 1)

        elif self.hub_type == self.NAMESPACES["b."]:

            if source.lower() in ("all", "docs"):
                for project in self.api.dm.get_projects():
                    self.projects.append(
                        Project(
                            project["attributes"]["name"],
                            project["id"][2:],
                            data=project,
                            app=self,
                        )
                    )

                    self._project_indices_by_id[project["id"][2:]] = (
                        len(self.projects) - 1
                    )
                    self._project_indices_by_name[
                        project["attributes"]["name"]
                    ] = (len(self.projects) - 1)

            if (
                source.lower() in ("all", "admin")
                and not self.auth.three_legged
            ):

                for project in self.api.hq.get_projects():
                    if project["id"] in self._project_indices_by_id:
                        self.projects[
                            self._project_indices_by_id[project["id"]]
                        ].data = project
                    else:
                        self.projects.append(
                            Project(
                                project["name"],
                                project["id"],
                                data=project,
                                app=self,
                            )
                        )
                        self._project_indices_by_id[project["id"]] = (
                            len(self.projects) - 1
                        )

                        self._project_indices_by_name[project["name"]] = (
                            len(self.projects) - 1
                        )

            elif source.lower() in ("all", "admin"):
                self.logger.warning(
                    "Failed to get projects. The BIM 360 API only supports 2-legged access tokens"  # noqa:E501
                )

    @_validate_bim360_hub
    def get_users(self):
        self.users = self.api.hq.get_users()
        self._user_indices_by_email = {
            user["email"]: i for i, user in enumerate(self.users)
        }

    @_validate_bim360_hub
    def get_companies(self):
        self.companies = self.api.hq.get_companies()
        self._company_indices_by_name = {
            company["name"]: i for i, company in enumerate(self.companies)
        }

    @_validate_bim360_hub
    def add_project(
        self,
        name,
        start_date=ForgeBase.TODAY_STRING,
        end_date=ForgeBase.IN_ONE_YEAR_STRING,
        template=None,
    ):

        if not getattr(self, "projects", None):
            self.projects = []
            self._project_indices_by_id = {}
            self._project_indices_by_name = {}

        if name not in self._project_indices_by_name:
            project = self.api.hq.post_project(
                name,
                start_date=start_date,
                end_date=end_date,
                template=template,
            )
            if project:
                self.projects.append(
                    Project(
                        project["name"], project["id"], app=self, data=project
                    )
                )
                self._project_indices_by_id[project["id"]] = (
                    len(self.projects) - 1
                )
                self._project_indices_by_name[project["name"]] = (
                    len(self.projects) - 1
                )
                return self.projects[-1]

    def find_project(self, value, key="name"):
        """key = name or id"""
        if key.lower() not in ("name", "id"):
            raise ValueError()

        if key == "name" and not getattr(self, "projects", None):
            self.get_projects()
        elif key == "id" and not getattr(self, "projects", None):
            project = self.api.dm.get_project(value, x_user_id=self.x_user_id)
            return Project(
                project["data"]["attributes"]["name"],
                project["data"]["id"][2:],
                data=project["data"],
                app=self,
            )

        try:
            if key.lower() == "name":
                return self.projects[self._project_indices_by_name[value]]
            elif key.lower() == "id":
                return self.projects[self._project_indices_by_id[value]]
        except KeyError:
            self.logger.warning("Project {}: {} not found".format(key, value))

    def find_user(self, email):
        if not getattr(self, "_user_indices_by_email", None):
            self.get_users()
        try:
            return self.users[self._user_indices_by_email[email]]
        except KeyError:
            self.logger.warning("User email: {} not found".format(email))

    def find_company(self, name):
        if not getattr(self, "_company_indices_by_name", None):
            self.get_companies()

        try:
            return self.companies[self._company_indices_by_name[name]]
        except KeyError:
            self.logger.warning("Company: {} not found".format(name))


class Project(ForgeBase):
    def __init__(
        self,
        name,
        project_id,
        app=None,
        data=None,
        x_user_id=None,
        include_hidden=False,
    ):
        self.name = name
        self.id = {"hq": project_id}
        if app:
            self.app = app
        if data:
            self.data = data
        if x_user_id:
            self.x_user_id = x_user_id
        self.include_hidden = include_hidden

    def __repr__(self):
        return "<Project - Name: {} - ID: {} at {}>".format(
            self.name, self.id, hex(id(self))
        )

    def _validate_app(func):
        def inner(self, *args, **kwargs):
            if not self.app:
                raise AttributeError("An 'app' attribute has not been defined")
            return func(self, *args, **kwargs)

        return inner

    def _validate_bim360_hub(func):
        def inner(self, *args, **kwargs):
            if self.app.hub_id[:2] != "b.":
                raise ValueError(
                    "The app.hub_id attribute must be a {} hub.".format(
                        ForgeBase.NAMESPACES["b."]
                    )
                )
            return func(self, *args, **kwargs)

        return inner

    def _validate_x_user_id(func):
        def inner(self, *args, **kwargs):
            if not self.app.auth.three_legged and not self.x_user_id:
                raise AttributeError(
                    "An 'x_user_id' attribute has not been defined"
                )
            return func(self, *args, **kwargs)

        return inner

    @property
    def app(self):
        if getattr(self, "_app", None):
            return self._app

    @app.setter
    def app(self, app):
        if not isinstance(app, ForgeApp):
            raise TypeError("Project.app must be a ForgeApp")
        elif not app.hub_id:
            raise AttributeError(
                "A 'hub_id' attribute has not been defined in your app"
            )
        else:
            self._app = app
            self.id["dm"] = app.hub_id[:2] + self.id["hq"]

    @property
    def data(self):
        if getattr(self, "_data", None):
            return self._data

    @data.setter
    def data(self, data):
        if not isinstance(data, dict):
            raise TypeError("Project.data must be a dictionary")
        else:
            if not getattr(self, "_data", None):
                self._data = {}
            if "account_id" in data:
                self._data["admin"] = data
            elif "attributes" in data:
                self._data["docs"] = data

    @_validate_app
    @_validate_bim360_hub
    def update(self, name=None, status=None):
        if self.app.auth.three_legged:
            raise ValueError(
                "The BIM 360 API only supports 2-legged access tokens"
            )

        if name or status:
            project = self.app.api.hq.patch_project(
                self.id["hq"], name=name, status=status, project_name=self.name
            )

            if project:
                if name and getattr(self.app, "projects", None):
                    try:
                        index = self.app._project_indices_by_name[self.name]
                        self.app._project_indices_by_name[name] = index
                        self.name = name
                    except Exception as e:
                        print(e)
                self.data = project

    @_validate_app
    def get_top_folders(self):
        data = []
        count = 0
        while not data:
            if count > 0:
                time.sleep(5)

            data = (
                self.app.api.dm.get_top_folders(
                    self.id["dm"], x_user_id=self.x_user_id
                ).get("data")
                or []
            )

            count += 1
            if count > 6:
                break

        self.top_folders = [
            Folder(
                folder["attributes"]["name"],
                folder["id"],
                extension_type=folder["attributes"]["extension"]["type"],
                data=folder,
                project=self,
            )
            for folder in data
        ]

        if self.top_folders:
            if self.app.hub_type == ForgeBase.NAMESPACES["a."]:
                self.project_files = self.top_folders[0]
                self.plans = None
            elif self.app.hub_type == ForgeBase.NAMESPACES["b."]:
                folder_names = [folder.name for folder in self.top_folders]
                self.project_files = (
                    self.top_folders[folder_names.index("Project Files")]
                    if "Project Files" in folder_names
                    else None
                )
                self.plans = (
                    self.top_folders[folder_names.index("Plans")]
                    if "Plans" in folder_names
                    else None
                )

        return self.top_folders

    def get_contents(self):
        if not getattr(self, "top_folders", None):
            self.get_top_folders()

        for folder in self.top_folders:
            folder.get_contents()

    @_validate_app
    @_validate_bim360_hub
    def get_roles(self):
        self.roles = self.app.api.hq.get_project_roles(self.id["hq"])
        return self.roles

    @_validate_app
    @_validate_bim360_hub
    @_validate_x_user_id
    def add_users(self, users, access_level="user", role_id=None):
        return self.app.api.hq.post_project_users(
            self.id["hq"],
            users,
            access_level=access_level,
            role_id=role_id,
            x_user_id=self.x_user_id,
            project_name=self.name,
        )

    @_validate_app
    @_validate_bim360_hub
    @_validate_x_user_id
    def update_user(
        self, user, company_id=None, role_id=None,
    ):
        return self.app.api.hq.patch_project_user(
            self.id["hq"],
            user,
            company_id=company_id,
            role_id=role_id,
            x_user_id=self.x_user_id,
            project_name=self.name,
        )

    def find(self, value, key="name"):
        """key = name or id or path"""
        if key.lower() not in ("name", "id", "path"):
            raise ValueError()

        if not getattr(self, "top_folders", None):
            self.get_contents()

        for folder in self.top_folders:
            if getattr(folder, key, None) == value:
                return folder
            else:
                for content, _ in folder._iter_contents():
                    if getattr(content, key, None) == value:
                        return content

        self.app.logger.warning(
            "{}: {} not found in '{}'".format(key, value, self.name)
        )

    def walk(self):
        if not getattr(self, "top_folders", None):
            self.get_contents()

        for folder in self.top_folders:
            print(folder.name)
            folder.walk(level=1)


class Content(object):
    def __init__(
        self,
        name,
        content_id,
        extension_type=None,
        data=None,
        project=None,
        host=None,
    ):
        self.name = name
        self.id = content_id
        self.extension_type = extension_type
        self.data = data
        self.path = "/{}".format(self.name)
        if project:
            self.project = project
        if host:
            self.host = host
            self.path = "{}{}".format(host.path, self.path)

    @property
    def extension_type(self):
        if getattr(self, "_extension_type", None):
            return self._extension_type

    @extension_type.setter
    def extension_type(self, extension_type):
        self._extension_type = extension_type
        self.deleted = extension_type in (
            ForgeApp.TYPES[ForgeApp.NAMESPACES["a."]]["versions"]["Deleted"],
            ForgeApp.TYPES[ForgeApp.NAMESPACES["b."]]["versions"]["Deleted"],
        )

    @property
    def project(self):
        if getattr(self, "_project", None):
            return self._project

    @project.setter
    def project(self, project):
        if not isinstance(project, Project):
            raise TypeError("Item.project must be a Project")
        elif not project.app:
            raise AttributeError(
                "A 'app' attribute has not been defined in your Project"
            )
        else:
            self._project = project

    @property
    def host(self):
        if getattr(self, "_host", None):
            return self._host

    @host.setter
    def host(self, host):
        if not isinstance(host, Folder):
            raise TypeError("Item.project must be a Project")
        elif not host.project:
            raise AttributeError(
                "A 'project' attribute has not been defined in your host"
            )
        else:
            self._host = host

    def _validate_project(func):
        def inner(self, *args, **kwargs):
            if not self.project:
                raise AttributeError(
                    "An 'project' attribute has not been defined."
                )
            return func(self, *args, **kwargs)

        return inner

    def _validate_host(func):
        def inner(self, *args, **kwargs):
            if not self.host:
                raise AttributeError(
                    "An 'host' attribute has not been defined."
                )
            return func(self, *args, **kwargs)

        return inner

    def _unpack_storage_id(self, storage_id):
        """returns bucket_key, object_name"""
        return storage_id.split(":")[-1].split("/")


class Folder(Content):
    def __init__(self, *args, **kwargs):
        """
        Args:
            name (``str``): The name of the folder.
            id (``str``): The id of the folder.

        Kwargs:
            data (``dict``): The data of the folder.
            project (``Project``): The Project where this folder is.
            host (``Folder``): The host folder.
        """
        super().__init__(*args, **kwargs)
        self.type = "folders"
        self.contents = []

    def _iter_contents(self, level=0):
        for content in self.contents:
            yield content, level
            if content.type == "folders":
                for sub_content, sub_level in content._iter_contents(
                    level=level + 1
                ):
                    yield sub_content, sub_level

    @Content._validate_project
    def get_contents(self):
        contents = self.project.app.api.dm.get_folder_contents(
            self.project.id["dm"],
            self.id,
            include_hidden=self.project.include_hidden,
            x_user_id=self.project.x_user_id,
        )

        for content in contents:
            if content["type"] == "items":
                self.contents.append(
                    Item(
                        content["attributes"]["displayName"],
                        content["id"],
                        extension_type=content["attributes"]["extension"][
                            "type"
                        ],
                        data=content,
                        project=self.project,
                        host=self,
                    )
                )
            elif content["type"] == "folders":
                self.contents.append(
                    Folder(
                        content["attributes"]["name"],
                        content["id"],
                        extension_type=content["attributes"]["extension"][
                            "type"
                        ],
                        data=content,
                        project=self.project,
                        host=self,
                    )
                )
                self.contents[-1].get_contents()

        return self.contents

    @Content._validate_project
    def add_sub_folder(self, folder_name):
        """
        """
        if not self.contents:
            self.get_contents()

        if self.contents:
            try:
                sub_folder_names = [
                    content.name
                    for content in self.contents
                    if content.type == "folders"
                ]

                if folder_name not in sub_folder_names:
                    folder = self.project.app.api.dm.post_folder(
                        self.project.id["dm"],
                        self.id,
                        folder_name,
                        project_name=self.project.name,
                        x_user_id=self.project.x_user_id,
                    )
                    self.get_contents()

                else:
                    index = sub_folder_names.index(folder_name)
                    folder = self.contents[index]
                    self.project.app.logger.warning(
                        "{}: folder '{}' already exists in '{}'".format(
                            self.project.name, folder_name, self.name
                        )
                    )
            except Exception as e:
                self.project.app.logger.warning(
                    "{}: couldn't add '{}' folder to '{}'".format(
                        self.name, folder_name, self.name
                    )
                )
                raise (e)
        else:
            folder = self.project.app.api.dm.post_folder(
                self.project.id["dm"],
                self.id,
                folder_name,
                project_name=self.project.name,
                x_user_id=self.project.x_user_id,
            )
            self.get_contents()
        return folder

    @Content._validate_project
    def _add_storage(self, name):
        return self.project.app.api.dm.post_storage(
            self.project.id["dm"],
            "folders",
            self.id,
            name,
            x_user_id=self.project.x_user_id,
        ).get("data")

    @Content._validate_project
    def _upload_file(self, storage_id, obj_bytes):
        bucket_key, object_name = self._unpack_storage_id(storage_id)
        return self.project.app.api.dm.put_object(
            bucket_key, object_name, obj_bytes
        )

    @Content._validate_project
    def add_item(
        self,
        name,
        storage_id=None,
        obj_bytes=None,
        item_extension_type=None,
        version_extension_type=None,
    ):
        """
        name include extension
        """
        if not storage_id and obj_bytes:
            storage_id = self._add_storage(name).get("id")

        if obj_bytes:
            self._upload_file(storage_id, obj_bytes)

        if not storage_id:
            return

        item = self.project.app.api.dm.post_item(
            self.project.id["dm"],
            self.id,
            storage_id,
            name,
            item_extension_type=item_extension_type,
            version_extension_type=version_extension_type,
            x_user_id=self.project.x_user_id,
        )

        if item.get("data"):
            return Item(
                item["data"]["attributes"]["displayName"],
                item["data"]["id"],
                extension_type=item["data"]["attributes"]["extension"]["type"],
                data=item["data"],
                project=self.project,
                host=self,
            )

    @Content._validate_project
    def copy_item(self, original_item):
        """
        name include extension
        """
        original_item.get_versions()
        storage = self._add_storage(original_item.name)
        item = self.project.app.api.dm.post_item(
            self.project.id["dm"],
            self.id,
            storage["id"],
            original_item.name,
            x_user_id=self.project.x_user_id,
            copy_from_id=original_item.versions[len(original_item.versions)][
                "id"
            ],
        )

        if item.get("data"):
            return Item(
                item["data"]["attributes"]["displayName"],
                item["data"]["id"],
                extension_type=item["data"]["attributes"]["extension"]["type"],
                data=item,
                project=self.project,
                host=self,
            )
        else:
            return item

    def find(self, value, key="name", shallow=True):
        """key = name or id or path"""
        if key.lower() not in ("name", "id", "path"):
            raise ValueError()

        if not self.contents:
            self.get_contents()

        for content, level in self._iter_contents():
            if shallow and level != 0:
                continue
            if getattr(content, key, None) == value:
                return content

        self.project.app.logger.warning(
            "{}: {} not found in '{}'".format(key, value, self.name)
        )

    def walk(self, level=0):
        if not self.contents:
            self.get_contents()

        for content, level in self._iter_contents(level=level):
            print("{}{}".format(" " * 4 * level, content.name))


class Item(Content):
    def __init__(self, *args, **kwargs):
        """
        Args:
            name (``str``): The name of the file including the file extension.
            id (``str``): The id of the file.

        Kwargs:
            data (``dict``): The data of the file.
            project (``Project``): The Project where this file is.
            host (``Folder``): The host folder.
        """
        super().__init__(*args, **kwargs)
        self.type = "items"
        self.versions = []
        self.storage_id = None

    @Content._validate_project
    def get_metadata(self):
        self.metadata = self.project.app.api.dm.get_item(
            self.project.id["dm"], self.id, x_user_id=self.project.x_user_id
        )

        self.hidden = self.metadata["data"]["attributes"]["hidden"]
        self.deleted = self.metadata["included"][0]["attributes"]["extension"][
            "type"
        ] in (
            ForgeApp.TYPES[ForgeApp.NAMESPACES["a."]]["versions"]["Deleted"],
            ForgeApp.TYPES[ForgeApp.NAMESPACES["b."]]["versions"]["Deleted"],
        )

        try:
            self.storage_id = self.metadata["included"][0]["relationships"][
                "storage"
            ]["data"]["id"]
            self.bucket_key, self.object_name = self._unpack_storage_id(
                self.storage_id
            )
        except KeyError:
            # no storage key
            pass

    @Content._validate_project
    @Content._validate_host
    def add_version(
        self,
        name,
        storage_id=None,
        obj_bytes=None,
        version_extension_type=None,
    ):
        """
        name include extension
        """
        if not storage_id and obj_bytes:
            storage_id = self.host._add_storage(name).get("id")

        if obj_bytes:
            self.host._upload_file(storage_id, obj_bytes)

        if not storage_id:
            return

        version = self.project.app.api.dm.post_item_version(
            self.project.id["dm"],
            storage_id,
            self.id,
            name,
            version_extension_type=version_extension_type,
            x_user_id=self.project.x_user_id,
        )

        # TODO - Marker
        # from .utils import pretty_print

        # pretty_print(version)

        self.versions.append(
            Version(
                int(version["data"]["attributes"]["versionNumber"]),
                version["data"]["id"],
                extension_type=version["data"]["attributes"]["extension"][
                    "type"
                ],
                item=self,
                data=version["data"],
            )
        )

    @Content._validate_project
    def get_versions(self):
        self.versions = [
            Version(
                int(version["attributes"]["versionNumber"]),
                version["id"],
                extension_type=version["attributes"]["extension"]["type"],
                item=self,
                data=version,
            )
            for version in self.project.app.api.dm.get_item_versions(
                self.project.id["dm"],
                self.id,
                x_user_id=self.project.x_user_id,
            )
            if version["type"] == "versions"
        ]
        self._version_indices_by_number = {
            version.number: i for i, version in enumerate(self.versions)
        }
        return self.versions

    @Content._validate_project
    def get_publish_status(self):
        return self.project.app.api.dm.get_publish_model_job(
            self.project.id["dm"], self.id, x_user_id=self.project.x_user_id
        )

    @Content._validate_project
    def publish(self):
        publish_status = self.get_publish_status()
        if not publish_status.get("errors") and not publish_status.get("data"):
            publish_job = self.project.app.api.dm.publish_model(
                self.project.id["dm"],
                self.id,
                x_user_id=self.project.x_user_id,
            )
            status = publish_job["data"]["attributes"]["status"]
            self.project.app.logger.info(
                "Published model. Status is '{}'".format(status)
            )
        elif not publish_status.get("errors"):
            status = publish_status["data"]["attributes"]["status"]
            self.project.app.logger.info(
                "Model did not need to be published. Latest version status is '{}'".format(  # noqa:E501
                    status
                )
            )
        else:
            status = None
            self.project.app.logger.info(
                "This item cannot need to be published"
            )

    @Content._validate_project
    def download(self, save=False, location=None):
        if not getattr(self, "metadata", None):
            self.get_metadata()

        if not getattr(self, "storage_id", None):
            self.project.app.logger.info(
                "File '{}': No data to download. Hidden: {}, Deleted: {}".format(  # noqa:E501
                    self.name, self.hidden, self.deleted
                )
            )
            self.bytes = None
            return

        self.project.app.logger.info("Downloading Item {}".format(self.name))
        self.bytes = self.project.app.api.dm.get_object(
            self.bucket_key, self.object_name
        )
        self.project.app.logger.info(
            "Download Finished - file size: {0:0.1f} MB".format(
                len(self.bytes) / 1024 / 1024
            )
        )
        if save and location and os.path.isdir(location):
            self.filepath = os.path.join(location, self.name)
            with open(self.filepath, "wb") as fp:
                fp.write(self.bytes)
            self.bytes = None

    def load(self):
        if getattr(self, "filepath", None):
            with open(self.filepath, "rb") as fp:
                self.bytes = fp.read()


class Version(Content):
    def __init__(
        self, number, version_id, extension_type=None, item=None, data=None
    ):
        self.number = number
        self.id = version_id
        self.extension_type = extension_type
        self.data = data
        if item:
            self.item = item

    @property
    def item(self):
        if getattr(self, "_item", None):
            return self._item

    @item.setter
    def item(self, item):
        if not isinstance(item, Item):
            raise TypeError("Version.item must be a Item")
        elif not item.project:
            raise AttributeError(
                "A 'project' attribute has not been defined in your Item"
            )
        else:
            self._item = item

    def _validate_item(func):
        def inner(self, *args, **kwargs):
            if not self.item:
                raise AttributeError(
                    "An 'item' attribute has not been defined."
                )
            return func(self, *args, **kwargs)

        return inner

    @_validate_item
    def get_metadata(self):
        self.metadata = self.item.project.app.api.dm.get_version(
            self.item.project.id["dm"],
            self.id,
            x_user_id=self.item.project.x_user_id,
        )
        if self.extension_type is None:
            self.extension_type = self.metadata["data"]["attributes"][
                "extension"
            ]["type"]

        try:
            self.storage_id = self.metadata["data"]["relationships"][
                "storage"
            ]["data"]["id"]
            self.bucket_key, self.object_name = self._unpack_storage_id(
                self.storage_id
            )
        except KeyError:
            self.storage_id = None

        self.file_size = self.metadata["data"]["attributes"]["storageSize"]

    @_validate_item
    def get_details(self):
        if not getattr(self, "metadata", None):
            self.get_metadata()

        if not getattr(self, "storage_id", None):
            self.item.project.app.logger.info(
                "File '{}' - Version '{}' : No data to download. Deleted: {}".format(  # noqa:E501
                    self.item.name, self.number, self.deleted
                )
            )
            return

        self.details = self.item.project.app.api.dm.get_object_details(
            self.bucket_key, self.object_name
        )
        try:
            self.storage_size = self.details["size"]
        except (KeyError, TypeError):
            self.storage_size = -1

    @_validate_item
    def transfer(
        self,
        target_host,
        target_item=None,
        chunk_size=5000000,
        force_create=False,
    ):
        """
        force_create to force create an item if item is not in target_host
        """
        self.get_details()

        if not getattr(self, "storage_size", None):
            self.item.project.app.logger.warning(
                "Couldn't add Version: {} of Item: '{}', because no data was found".format(  # noqa: E501
                    self.number, self.item.name
                )
            )
            return

        # find item to add version
        target_item = target_item or target_host.find(self.item.name)

        if not target_item and (not force_create and self.number != 1):
            self.item.project.app.logger.warning(
                "Couldn't add Version: {} of Item: '{}' because no Item found".format(  # noqa: E501
                    self.number, self.item.name
                )
            )
            return

        elif target_item:
            target_item.get_versions()
            if len(target_item.versions) == self.number:
                self.item.project.app.logger.warning(
                    "Couldn't add Version: {} of Item: '{}' because Version already exists".format(  # noqa: E501
                        self.number, self.item.name
                    )
                )
                return
            elif len(target_item.versions) != self.number - 1:
                self.item.project.app.logger.warning(
                    "Couldn't add Version: {} of Item: '{}' because Item has {} versions".format(  # noqa: E501
                        self.number, self.item.name, len(target_item.versions)
                    )
                )
                return

        tg_storage_id = target_host._add_storage(self.item.name).get("id")
        tg_bucket_key, tg_object_name = self._unpack_storage_id(tg_storage_id)

        self.item.project.app.logger.info(
            "Beginning transfer of: '{}' - version: {}".format(
                self.item.name, self.number
            )
        )

        pbar = tqdm(
            total=self.storage_size,
            unit="iB",
            unit_scale=True,
            desc="Transferring - {}".format(self.item.name),
        )

        data_left = self.storage_size
        count = 0
        while data_left > 0:
            lower = count * chunk_size
            upper = lower + chunk_size
            if upper > self.storage_size:
                upper = self.storage_size
            upper -= 1

            chunk = self.item.project.app.api.dm.get_object(
                self.bucket_key, self.object_name, byte_range=(lower, upper),
            )

            target_host.project.app.api.dm.put_object_resumable(
                tg_bucket_key,
                tg_object_name,
                chunk,
                self.storage_size,
                (lower, upper),
            )

            pbar.update(chunk_size)
            data_left -= chunk_size
            count += 1

        pbar.close()

        version_extension_type = ForgeBase._convert_extension_type(
            self.extension_type, target_host.project.app.hub_type
        )

        if force_create or self.number == 1:
            item_extension_type = ForgeBase._convert_extension_type(
                self.item.extension_type, target_host.project.app.hub_type
            )
            target_host.add_item(
                self.item.name,
                storage_id=tg_storage_id,
                item_extension_type=item_extension_type,
                version_extension_type=version_extension_type,
            )
        else:
            # TODO - Marker
            # print(self.item.name)
            # print(tg_storage_id)
            # print(version_extension_type)
            # print(target_item.project.name)
            # print(target_item.project.id)
            # print(target_item.id)
            target_item.add_version(
                self.item.name,
                storage_id=tg_storage_id,
                version_extension_type=version_extension_type,
            )

        self.item.project.app.logger.info(
            "Finished transfer of: '{}' version: '{}'".format(
                self.item.name, self.number
            )
        )
