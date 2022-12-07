# Copyright 2022 The DLRover Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import copy
from datetime import datetime

from dlrover.python.common.constants import (
    NodeExitReason,
    NodeResourceLimit,
    NodeStatus,
)


class NodeResource(object):
    """NodeResource records a resource of a Node.
    Attributes:
        cpu: float, CPU cores.
        memory: float, memory MB.
        gpu_type: str, the type of GPU.
        gpu_num: int,
        image: the image name of the node.
        priority: the priority classs of the node.
    """

    def __init__(self, cpu, memory, gpu_type=None, gpu_num=0):
        self.cpu = cpu
        self.memory = memory
        self.gpu_type = gpu_type
        self.gpu_num = gpu_num
        self.image = ""
        self.priority = ""

    def to_resource_dict(self):
        resource = {"cpu": self.cpu, "memory": str(self.memory) + "Mi"}
        if self.gpu_num > 0:
            resource[self.gpu_type] = self.gpu_num
        return resource

    @classmethod
    def resource_str_to_node_resource(cls, resource_str):
        """Convert the resource configuration like "memory=100Mi,cpu=5"
        to a NodeResource instance."""
        resource = {}
        if not resource_str:
            return NodeResource(0, 0)
        for value in resource_str.strip().split(","):
            resource[value.split("=")[0]] = value.split("=")[1]

        memory = float(resource.get("memory", "0Mi")[0:-2])
        cpu = float(resource.get("cpu", "0"))
        gpu_type = None
        gpu_num = 0
        for key, _ in resource.items():
            if "nvidia.com" in key:
                gpu_type = key
                gpu_num = int(resource[key])
        return NodeResource(cpu, memory, gpu_type, gpu_num)

    @classmethod
    def convert_memory_to_mb(cls, memory: str):
        unit = memory[-2:]
        value = int(memory[0:-2])
        if unit == "Gi":
            value = value * 1024
        elif unit == "Ki":
            value = int(value / 1024)
        return value


class NodeGroupResource(object):
    """The node group resource contains the number of the task
    and resource (cpu, memory) of each task.
    Args:
        count: int, the number of task.
        node_resource: a NodeResource instance.
    """

    def __init__(self, count, node_resource: NodeResource, priority=None):
        self.count = count
        self.node_resource = node_resource
        self.priority = priority

    def update(self, count, cpu, memory):
        self.count = count
        self.node_resource.cpu = cpu
        self.node_resource.memory = memory

    @classmethod
    def new_empty(cls):
        return NodeGroupResource(0, NodeResource(0, 0))


class Node(object):
    """Node records the information of each training node.
    Attributes:
        type: str, the type (e.g. "ps", "worker") of a node.
        id: int, the id of a node.
        name: str, the name of a node.
        status: the status of a node.
        start_time: int, the start timestamp of a node.
        task_index: int, the task index of a node in a training cluster.
        relaunch_count: int, the relaunched number of the training node.
        critical: bool, if true, the job will fail if the node fails.
        max_relaunch_count: int, the maximum to relaunch a node.
        relaunchable: bool, whether to relaunch a node if it fails.
        is_released: bool, whether to released the node.
        exit_reason: str, the exited reason of a node.
        used_resource: the resource usage of the node.
    """

    def __init__(
        self,
        node_type,
        node_id,
        config_resource: NodeResource,
        name=None,
        status=NodeStatus.INITIAL,
        start_time=None,
        task_index=None,
        relaunch_count=0,
        critical=False,
        max_relaunch_count=0,
        relaunchable=True,
        service_addr=None,
    ):
        self.type = node_type
        self.id = node_id
        self.name = name
        self.status = status
        self.start_time = start_time
        self.task_index = task_index if task_index is not None else node_id
        self.relaunch_count = relaunch_count
        self.critical = critical
        self.max_relaunch_count = max_relaunch_count
        self.relaunchable = relaunchable
        self.service_addr = service_addr

        now = datetime.now()
        self.create_time = now
        self.finish_time = now
        self.is_recovered_oom = False
        self.is_released = False
        self.exit_reason = None
        self.config_resource = config_resource
        self.used_resource = NodeResource(0.0, 0.0)

    def inc_relaunch_count(self):
        self.relaunch_count += 1

    def update_info(
        self,
        name=None,
        start_time=None,
        create_time=None,
    ):
        if name is not None:
            self.name = name
        if start_time is not None:
            self.start_time = start_time
        if create_time is not None:
            self.create_time = create_time

    def update_status(self, status=None):
        if status is not None:
            self.status = status

    def update_resource_usage(self, cpu, memory):
        self.used_resource.cpu = cpu
        self.used_resource.memory = memory

    def get_relaunch_node_info(self, new_id):
        new_node = copy.deepcopy(self)
        new_node.id = new_id
        new_node.name = None
        new_node.status = NodeStatus.INITIAL
        new_node.start_time = None
        new_node.is_released = False
        new_node.relaunchable = True
        return new_node

    def is_unrecoverable_failure(self):
        if (
            self.relaunch_count >= self.max_relaunch_count
            or self.exit_reason == NodeExitReason.FATAL_ERROR
            or self.used_resource.memory >= NodeResourceLimit.MAX_MEMORY
        ):
            return True
        return False

    def set_exit_reason(self, reason):
        self.exit_reason = reason