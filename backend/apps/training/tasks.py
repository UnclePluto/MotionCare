from celery import shared_task


@shared_task
def run_motion_analysis_job(job_id):
    raise NotImplementedError(f"动作分析任务尚未实现: {job_id}")
