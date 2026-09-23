import json
import os
import uuid
import boto3
from chess_engine import ChessValidator

dynamodb = boto3.resource('dynamodb')
ses = boto3.client('ses')
s3 = boto3.client('s3')

TABLE_NAME = os.environ.get('TABLE_NAME')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', '2030.lida@gmail.com')
UPLOAD_BUCKET = os.environ.get('UPLOAD_BUCKET')

table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None

def submit_handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        email = body.get('email')
        moves = body.get('moves')

        if not email or not moves:
            return {
                'statusCode': 400,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Email und Zuege erforderlich'})
            }

        submission_id = str(uuid.uuid4())
        token = str(uuid.uuid4())

        table.put_item(
            Item={
                'id': submission_id,
                'email': email,
                'moves': moves,
                'status': 'AWAITING_CONFIRMATION',
                'confirmation_token': token
            }
        )

        domain = event.get('requestContext', {}).get('domainName', '')
        stage = event.get('requestContext', {}).get('stage', '')
        base_url = f"https://{domain}" if not stage or stage == '$default' else f"https://{domain}/{stage}"
        confirm_url = f"{base_url}/confirm?id={submission_id}&token={token}"

        ses.send_email(
            Source=SENDER_EMAIL,
            Destination={'ToAddresses': [email]},
            Message={
                'Subject': {'Data': 'Checkmate Replay Hub - Bestaetigung'},
                'Body': {
                    'Text': {
                        'Data': f"Bitte bestaetigen Sie Ihre Einreichung:\n{confirm_url}"
                    }
                }
            }
        )

        return {
            'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'submissionId': submission_id,
                'status': 'AWAITING_CONFIRMATION'
            })
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }

def confirm_handler(event, context):
    params = event.get('queryStringParameters') or {}
    submission_id = params.get('id')
    token = params.get('token')

    if not submission_id or not token:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'text/html; charset=utf-8'},
            'body': '<h2>Ungueltiger Link</h2><p>Parameter fehlen.</p>'
        }

    try:
        response = table.get_item(Key={'id': submission_id})
        item = response.get('Item')

        if not item:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'text/html; charset=utf-8'},
                'body': '<h2>Einreichung nicht gefunden</h2>'
            }

        if item.get('status') in ['PROCESSING', 'DONE', 'FAILED']:
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'text/html; charset=utf-8'},
                'body': f"<h2>Bereits bestaetigt</h2><p>Aktueller Status: {item.get('status')}</p>"
            }

        if item.get('confirmation_token') != token:
            return {
                'statusCode': 403,
                'headers': {'Content-Type': 'text/html; charset=utf-8'},
                'body': '<h2>Ungueltiger Token</h2><p>Link abgelaufen oder unguetlig.</p>'
            }

        table.update_item(
            Key={'id': submission_id},
            UpdateExpression="SET #st = :p REMOVE confirmation_token",
            ExpressionAttributeNames={'#st': 'status'},
            ExpressionAttributeValues={':p': 'PROCESSING'}
        )

        validator = ChessValidator()
        moves_data = item.get('moves', '')
        email = item.get('email')

        is_valid, message, count, winner = validator.validate_and_play(moves_data)
        board_image_url = None

        if is_valid:
            final_status = 'DONE'
            svg_content = validator.generate_board_svg()
            image_key = f"boards/{submission_id}.svg"
            s3.put_object(
                Bucket=UPLOAD_BUCKET,
                Key=image_key,
                Body=svg_content.encode('utf-8'),
                ContentType='image/svg+xml'
            )
            board_image_url = f"https://{UPLOAD_BUCKET}.s3.amazonaws.com/{image_key}"

            email_subject = 'Checkmate Replay Hub - Auswertung: Gueltig (DONE)'
            email_html = f"""
            <h2>Ihre Partie wurde erfolgreich ausgewertet!</h2>
            <p><strong>Status:</strong> DONE</p>
            <p><strong>Gewinner:in:</strong> {winner}</p>
            <p><strong>Gespielte Zuege:</strong> {count}</p>
            <h3>Endposition des Schachbretts:</h3>
            <p><a href="{board_image_url}" target="_blank">Klicken Sie hier, um das Schachbrettbild separat anzuzeigen</a></p>
            <div>{svg_content}</div>
            """
            email_text = f"Status: DONE\nGewinner:in: {winner}\nZuege: {count}\nBild: {board_image_url}"
        else:
            final_status = 'FAILED'
            email_subject = 'Checkmate Replay Hub - Auswertung: Fehlgeschlagen (FAILED)'
            email_html = f"""
            <h2>Ihre Partie konnte nicht validiert werden.</h2>
            <p><strong>Status:</strong> FAILED</p>
            <p><strong>Fehlergrund:</strong> {message}</p>
            <p><strong>Ausgefuehrte Zuege bis zum Fehler:</strong> {count}</p>
            """
            email_text = f"Status: FAILED\nGrund: {message}\nZuege: {count}"

        table.update_item(
            Key={'id': submission_id},
            UpdateExpression="SET #st = :s, #res = :r",
            ExpressionAttributeNames={'#st': 'status', '#res': 'result_details'},
            ExpressionAttributeValues={
                ':s': final_status,
                ':r': {
                    'message': message,
                    'move_count': count,
                    'winner': str(winner),
                    'board_image_url': board_image_url
                }
            }
        )

        ses.send_email(
            Source=SENDER_EMAIL,
            Destination={'ToAddresses': [email]},
            Message={
                'Subject': {'Data': email_subject},
                'Body': {
                    'Text': {'Data': email_text},
                    'Html': {'Data': email_html}
                }
            }
        )

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'text/html; charset=utf-8'},
            'body': f"<h2>Erfolgreich ausgewertet!</h2><p>Status: {final_status}</p><p>{message}</p>"
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'text/html; charset=utf-8'},
            'body': f'<h2>Fehler bei der Auswertung</h2><p>{str(e)}</p>'
        }

def status_handler(event, context):
    params = event.get('queryStringParameters') or {}
    submission_id = params.get('id')

    if not submission_id:
        return {
            'statusCode': 400,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'id erforderlich'})
        }

    try:
        response = table.get_item(Key={'id': submission_id})
        item = response.get('Item')
        if not item:
            return {
                'statusCode': 404,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Nicht gefunden'})
            }

        return {
            'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'status': item.get('status'),
                'result_details': item.get('result_details')
            })
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }