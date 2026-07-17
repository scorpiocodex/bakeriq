import { useQuery, useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { fetchRegistrationToken, submitRegistration } from '../lib/api';

/**
 * Registration hook — encapsulates load/edit/submit lifecycle for a
 * registration webform token.
 *
 * Mirrors useCart.js pattern:
 *   - useQuery for the initial GET
 *   - useMutation for the POST submit
 *   - status enum ('loading' | 'error' | 'ready' | 'submitted' |
 *     'already_registered')
 *   - form state kept locally with useState (server owns validation
 *     on submit)
 *
 * Returns:
 *   - status: string enum
 *   - tokenData: { phone, already_registered } from GET
 *   - form: { name, address_line_1, address_line_2, city, state, pincode }
 *   - setField: (fieldName, value) => void
 *   - submit: () => Promise
 *   - submitError: axios error if submit failed
 *   - loadError: axios error if the initial GET failed
 *   - isSubmitting: boolean
 *   - submittedResult: { message, registration_id } on success
 */
export function useRegistration(token) {
  // Initial GET — is the token valid + what's the phone?
  const tokenQuery = useQuery({
    queryKey: ['registration-token', token],
    queryFn: () => fetchRegistrationToken(token),
    enabled: !!token,
    retry: false, // Don't retry — 404/410/409 are terminal
  });

  // Form state — controlled inputs, plain useState
  const [form, setForm] = useState({
    name: '',
    address_line_1: '',
    address_line_2: '',
    city: '',
    state: 'Kerala', // sensible default; user can override
    pincode: '',
  });

  function setField(fieldName, value) {
    setForm((prev) => ({ ...prev, [fieldName]: value }));
  }

  // Submit mutation
  const submitMutation = useMutation({
    mutationFn: () => {
      // Trim + strip empty optional fields so the server sees null
      // rather than empty string. Backend service already handles
      // this defensively, but sending clean input is cleaner.
      const payload = {
        name: form.name.trim(),
      };
      // Only include address fields if they have content
      const addressFields = ['address_line_1', 'address_line_2', 'city', 'state', 'pincode'];
      addressFields.forEach((field) => {
        const value = form[field]?.trim();
        if (value) {
          payload[field] = value;
        }
      });
      return submitRegistration(token, payload);
    },
    retry: false, // Don't auto-retry submits — user should see errors
  });

  // Status enum
  let status;
  if (tokenQuery.isLoading) {
    status = 'loading';
  } else if (tokenQuery.isError) {
    status = 'error';
  } else if (tokenQuery.data?.already_registered) {
    status = 'already_registered';
  } else if (submitMutation.isSuccess) {
    status = 'submitted';
  } else {
    status = 'ready';
  }

  return {
    status,
    tokenData: tokenQuery.data,
    form,
    setField,
    submit: () => submitMutation.mutateAsync(),
    submitError: submitMutation.error,
    loadError: tokenQuery.error,
    isSubmitting: submitMutation.isPending,
    submittedResult: submitMutation.data,
  };
}
