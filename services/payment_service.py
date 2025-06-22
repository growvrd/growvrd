class PaymentService:
    def create_checkout(self, data):
        return {
            'checkout_id': 'ch_' + str(hash(str(data)))[:20],
            'amount': data.get('amount', 0),
            'status': 'pending'
        }
    
    def verify_payment(self, payment_id):
        return {'status': 'succeeded', 'id': payment_id}
