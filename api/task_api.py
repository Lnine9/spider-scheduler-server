from utils.flask_ext.flask_app import BlueprintAppApi
from service.task_service import TaskService
from flask import request
from utils.index import clean_params

task_api = BlueprintAppApi(name="task", import_name=__name__)

@task_api.get('/get_task_by_project_id')
def get_task_by_project_id():
    project_id = request.args.get('project_id')
    return TaskService.get_task_by_project_id(project_id)

@task_api.post('/update_task_status')
def update_task_status():
    data = request.json
    task_id = data.get('task_id')
    return TaskService.update_task_status(task_id, data)

