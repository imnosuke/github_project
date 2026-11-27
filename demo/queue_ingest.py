"""Queue one historical GH Archive hour when the demo starts."""

from time import sleep

from airflow.api.common.trigger_dag import trigger_dag
from airflow.exceptions import DagNotFound, DagRunAlreadyExists


def main():
    for _ in range(60):
        try:
            run = trigger_dag(
                dag_id="gharchive_to_minio_hourly",
                run_id="reposcope-demo__2025-01-15T14",
                conf={"custom_date": "2025-01-15", "custom_hour": 14},
                replace_microseconds=False,
            )
        except DagRunAlreadyExists:
            print("Demo ingestion run already exists.")
            return
        except DagNotFound:
            sleep(2)
        else:
            if run is None:
                raise RuntimeError("Airflow did not create the demo run.")
            print(f"Queued Airflow run {run.run_id}.")
            return
    raise RuntimeError("Airflow did not register gharchive_to_minio_hourly within 120 seconds.")


if __name__ == "__main__":
    main()
