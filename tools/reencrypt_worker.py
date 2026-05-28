#!/usr/bin/env python3
"""Background worker to process re-encrypt jobs from the database.

Usage:
  python3 tools/reencrypt_worker.py --once
  python3 tools/reencrypt_worker.py         # run continuously

This worker is intentionally simple: it claims the oldest queued job, marks it in_progress,
computes total_count, and processes `encuestas` in batches updating job progress.
"""

import argparse
import time
import datetime
import sys
import traceback

from app import get_conn, decrypt_data, encrypt_data, log


def claim_job(c):
    c.execute("SELECT * FROM reencrypt_jobs WHERE status IN ('queued','in_progress') ORDER BY created_at ASC LIMIT 1")
    return c.fetchone()


def set_job_started(conn, c, job_id):
    now = str(datetime.datetime.now())
    c.execute("UPDATE reencrypt_jobs SET status='in_progress', started_at=?, last_update=? WHERE id=?", (now, now, job_id))
    conn.commit()


def update_job_progress(conn, c, job_id, processed_count, total_count, notes=None):
    now = str(datetime.datetime.now())
    c.execute(
        "UPDATE reencrypt_jobs SET processed_count=?, total_count=?, last_update=?, notes=? WHERE id=?",
        (processed_count, total_count, now, notes, job_id),
    )
    conn.commit()


def finish_job(conn, c, job_id, success=True, notes=None):
    now = str(datetime.datetime.now())
    status = 'finished' if success else 'failed'
    c.execute("UPDATE reencrypt_jobs SET status=?, finished_at=?, last_update=?, notes=? WHERE id=?", (status, now, now, notes, job_id))
    conn.commit()


def compute_total_count(c, new_fp):
    c.execute("SELECT COUNT(1) as cnt FROM encuestas WHERE encryption_key_fingerprint != ?", (new_fp,))
    row = c.fetchone()
    return int(row[0]) if row else 0


def process_job(job, batch_size=500, batch_sleep=0.5):
    conn = get_conn()
    c = conn.cursor()
    job_id = job['id']
    new_fp = job['new_key_fingerprint']
    requested_by = job['requested_by']

    set_job_started(conn, c, job_id)

    total_count = compute_total_count(c, new_fp)
    processed = int(job.get('processed_count') or 0)
    update_job_progress(conn, c, job_id, processed, total_count, notes='started')

    try:
        while True:
            c.execute(
                "SELECT id, datos, encryption_key_fingerprint FROM encuestas WHERE encryption_key_fingerprint != ? ORDER BY id ASC LIMIT ?",
                (new_fp, batch_size),
            )
            rows = c.fetchall()
            if not rows:
                break

            batch_processed = 0
            for row in rows:
                enc_id = row[0]
                blob = row[1]
                try:
                    payload = decrypt_data(blob, log_events=False)
                    if payload is None:
                        # record failure in notes and skip
                        log('sistema', f'Fallo descifrado durante reencrypt job {job_id} id={enc_id}', categoria='seguridad')
                        continue

                    refreshed = encrypt_data(payload)
                    now = str(datetime.datetime.now())
                    c.execute(
                        "UPDATE encuestas SET datos=?, encryption_key_fingerprint=?, encrypted_at=?, updated_at=? WHERE id=?",
                        (refreshed, new_fp, now, now, enc_id),
                    )
                    batch_processed += 1
                except Exception as e:
                    log('sistema', f'Error re-encrypt id={enc_id}: {e}', categoria='seguridad', detalle=str(e))
                    continue

            conn.commit()
            processed += batch_processed
            update_job_progress(conn, c, job_id, processed, total_count, notes=f'processed {processed}/{total_count}')

            if batch_sleep:
                time.sleep(batch_sleep)

        finish_job(conn, c, job_id, success=True, notes=f'completed {processed}/{total_count}')
        log(requested_by or 'sistema', f'Completed re-encrypt job {job_id}: {processed}/{total_count}', categoria='seguridad')
    except Exception as e:
        traceback.print_exc()
        finish_job(conn, c, job_id, success=False, notes=str(e))
        log('sistema', f'Failed re-encrypt job {job_id}: {e}', categoria='seguridad')
    finally:
        conn.close()


def run_loop(poll_interval=5, batch_size=500, batch_sleep=0.5, once=False):
    while True:
        conn = get_conn()
        c = conn.cursor()
        job = claim_job(c)
        if job:
            job = dict(job)
        if job:
            # If job was queued, ensure it's marked started
            if job['status'] == 'queued':
                set_job_started(conn, c, job['id'])
                # recompute job row
                c.execute("SELECT * FROM reencrypt_jobs WHERE id=?", (job['id'],))
                row = c.fetchone()
                job = dict(row) if row else None

            # compute total_count if not set
            total = job.get('total_count')
            if not total:
                total = compute_total_count(c, job['new_key_fingerprint'])
                c.execute("UPDATE reencrypt_jobs SET total_count=? WHERE id=?", (total, job['id']))
                conn.commit()

            conn.close()
            process_job(job, batch_size=batch_size, batch_sleep=batch_sleep)
            if once:
                break
        else:
            conn.close()
            if once:
                print('No queued jobs. Exiting.')
                break
            time.sleep(poll_interval)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true', help='Run one job then exit')
    parser.add_argument('--poll-interval', type=float, default=5.0, help='Seconds to wait between polls')
    parser.add_argument('--batch-size', type=int, default=500, help='Number of records per batch')
    parser.add_argument('--batch-sleep', type=float, default=0.5, help='Seconds to sleep between batches')

    args = parser.parse_args()

    run_loop(poll_interval=args.poll_interval, batch_size=args.batch_size, batch_sleep=args.batch_sleep, once=args.once)


if __name__ == '__main__':
    main()
