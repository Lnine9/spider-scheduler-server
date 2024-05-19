from scrapyd_api import ScrapydClient
from model.scrapyd_node import ScrapydNode
from utils.logger import logger
from model.task import Task
from model.spider_info import SpiderInfo
from constants.index import TaskStatus
from setting import SCRAPY_PROJECT
from service.scheduler import scheduler
from shutil import copyfileobj

class Client:
    def __init__(self, id, name, address, instance):
        self.id = id
        self.name = name
        self.address = address
        self.instance = instance


clients = []


class ScrapydService:

    @classmethod
    def init(cls):
        cls.connect_nodes()

    @classmethod
    def connect_nodes(cls):
        global clients
        records = ScrapydNode.select().dicts()
        clients = []

        for record in records:
            try:
                client_instance = ScrapydClient(record['address'])
                clients.append(Client(record['id'], record['name'], record['address'], client_instance))
            except Exception as e:
                clients.append(Client(record['id'], record['name'], record['address'], None))

    @classmethod
    def list_scrapyd_node(cls):
        result = []
        for c in clients:
            status = 0
            if c.instance is not None:
                try:
                    deamon_status = c.instance.daemon_status()
                    if deamon_status.get('status') == 'ok':
                        status = 1
                except Exception as e:
                    status = 0

            result.append({
                'id': c.id,
                'name': c.name,
                'address': c.address,
                'status': status
            })

        return {
            'list': result,
            'total': len(result)
        }

    @classmethod
    def get_node_detail(cls, id):
        for c in clients:
            if str(c.id) == str(id):
                if c.instance is not None:
                    try:
                        data = c.instance.daemon_status()
                        data.update({
                            'id': c.id,
                            'name': c.name,
                            'address': c.address,
                            'status': 1,
                        })
                        return data
                    except Exception as e:
                        pass
                return {
                    'id': c.id,
                    'name': c.name,
                    'address': c.address,
                    'status': 0,
                }
        return None

    @classmethod
    def add_node(cls, node):
        ScrapydNode.create(**node)
        cls.connect_nodes()
        return node

    @classmethod
    def delete_node(cls, id):
        node = ScrapydNode.get(ScrapydNode.id == id)
        node.delete_instance()
        cls.connect_nodes()
        return True

    @classmethod
    def get_node_by_id(cls, id):
        for c in clients:
            if str(c.id) == str(id):
                return c
        return None

    @classmethod
    def get_least_busy_node(cls):
        least_busy = None
        for c in clients:
            if c.instance is not None:
                try:
                    if c.instance.daemon_status().get('status') != 'ok':
                        continue
                    data = c.instance.list_projects()
                    if least_busy is None or len(data) < least_busy:
                        least_busy = c
                except Exception as e:
                    pass
        return least_busy

    @classmethod
    def execute_task(cls, task_id, node_id):
        print(task_id, node_id)
        task = Task.get(Task.id == task_id)
        if task is None:
            return
        if task.status == TaskStatus.SCHEDULED or task.status == TaskStatus.COMPLETED:
            return

        spider = SpiderInfo.get(SpiderInfo.id == task.spider_id)
        if spider is None:
            return

        params = dict(task.__data__)
        params.update({
            'task_id': params.get('id'),
        })

        if node_id is not None:
            node = cls.get_node_by_id(node_id)
            if node is not None:
                try:
                    node.instance.schedule(project=SCRAPY_PROJECT['NAME'], spider=spider.main_class, jobid=task_id, **params)
                    task.status = TaskStatus.SCHEDULED
                    task.job_id = task_id
                    task.node_address = node.address
                    task.save()
                except Exception as e:
                    logger.error(f"Failed to execute task {task_id} on node {node_id}: {e}")
                    raise e
        else:
            node = cls.get_least_busy_node()
            if node is not None:
                try:
                    node.instance.schedule(project=SCRAPY_PROJECT['NAME'], spider=spider.main_class, jobid=task_id, **params)
                    task.status = TaskStatus.SCHEDULED
                    task.job_id = task_id
                    task.node_address = node.address
                    task.save()
                except Exception as e:
                    logger.error(f"Failed to execute task {task_id} on node {node.id}: {e}")
                    raise e

    @classmethod
    def update_egg(cls, egg):
        for c in clients:
            if c.instance is not None:
                try:
                    c.instance.daemon_status()
                except Exception as e:
                    continue
                try:
                    c.instance.add_version(project=SCRAPY_PROJECT['NAME'], egg=egg)
                except Exception as e:
                    logger.error(f"Failed to update egg on node {c.id}: {e}")
                    raise e
        return

    @classmethod
    def update_node_egg(cls, node_id, egg):
        node = cls.get_node_by_id(node_id)
        if node is not None:
            try:
                node.instance.daemon_status()
            except Exception as e:
                return False
            try:
                node.instance.add_version(project=SCRAPY_PROJECT['NAME'], egg=egg)
            except Exception as e:
                logger.error(f"Failed to update egg on node {node_id}: {e}")
                raise e
        return


scheduler.add_job(
    id='auto_connect_nodes',
    func=ScrapydService.connect_nodes,
    trigger='cron',
    second=30,
    replace_existing=True,
)
