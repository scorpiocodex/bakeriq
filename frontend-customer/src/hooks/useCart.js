import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useEffect } from 'react';
import { fetchCart, saveCart, placeOrder } from '../lib/api';

/**
 * Cart hook — encapsulates load/edit/save/place lifecycle for a token.
 *
 * Returns:
 *   - status: 'loading' | 'error' | 'ready' | 'placed'
 *   - cart: server-loaded cart payload (kind, customer, items, menu, total)
 *   - items: local working copy (quantity edits live here until save)
 *   - total: client-computed total based on items
 *   - error: error object if load failed
 *   - updateQuantity: (product_id, newQuantity) => void
 *   - addItem: (product) => void
 *   - removeItem: (product_id) => void
 *   - save: () => Promise — calls POST /cart/<token>
 *   - place: () => Promise — calls POST /cart/<token>/place
 *   - saveStatus: 'idle' | 'pending' | 'success' | 'error'
 *   - placeStatus: 'idle' | 'pending' | 'success' | 'error'
 *   - placedOrder: result of the place mutation if placed
 */
export function useCart(token) {
  const queryClient = useQueryClient();

  // Server-loaded cart
  const cartQuery = useQuery({
    queryKey: ['cart', token],
    queryFn: () => fetchCart(token),
    enabled: !!token,
  });

  // Local working copy. Initialised once the server data lands; further
  // user edits mutate this rather than going through react-query so the
  // UI feels instant.
  const [items, setItems] = useState([]);

  useEffect(() => {
    if (cartQuery.data?.items) {
      setItems(cartQuery.data.items);
    }
  }, [cartQuery.data]);

  // Client-side total — recomputed on every edit for instant feedback.
  // Server is authoritative on save/place.
  const total = items.reduce((sum, item) => sum + item.subtotal, 0);

  function updateQuantity(productId, newQuantity) {
    setItems((prev) =>
      prev.map((item) => {
        if (item.product_id !== productId) return item;
        const quantity = Math.max(0, newQuantity);
        return {
          ...item,
          quantity,
          subtotal: item.unit_price * quantity,
        };
      }),
    );
  }

  function addItem(product) {
    setItems((prev) => {
      // If already in cart, increment instead of duplicating
      const existing = prev.find((i) => i.product_id === product.id);
      if (existing) {
        return prev.map((i) =>
          i.product_id === product.id
            ? { ...i, quantity: i.quantity + 1, subtotal: i.unit_price * (i.quantity + 1) }
            : i,
        );
      }
      return [
        ...prev,
        {
          product_id: product.id,
          product_name: product.name,
          unit_price: product.unit_price,
          unit_label: product.unit_label,
          quantity: 1,
          subtotal: product.unit_price,
        },
      ];
    });
  }

  function removeItem(productId) {
    setItems((prev) => prev.filter((i) => i.product_id !== productId));
  }

  // Strip out zero-qty items before sending to server
  const itemsForServer = () =>
    items
      .filter((i) => i.quantity > 0)
      .map((i) => ({ product_id: i.product_id, quantity: i.quantity }));

  const saveMutation = useMutation({
    mutationFn: () => saveCart(token, itemsForServer()),
    onSuccess: (data) => {
      // Server returns the canonical items list (with current prices).
      // Update our local copy so prices reflect any backend revalidation.
      if (data?.items) {
        setItems(data.items);
      }
      queryClient.invalidateQueries({ queryKey: ['cart', token] });
    },
  });

  const placeMutation = useMutation({
    mutationFn: () => placeOrder(token, itemsForServer()),
  });

  let status = 'loading';
  if (cartQuery.isError) status = 'error';
  else if (placeMutation.isSuccess) status = 'placed';
  else if (cartQuery.data) status = 'ready';

  return {
    status,
    cart: cartQuery.data,
    items,
    total,
    error: cartQuery.error,
    updateQuantity,
    addItem,
    removeItem,
    save: () => saveMutation.mutateAsync(),
    place: () => placeMutation.mutateAsync(),
    saveStatus: saveMutation.status,
    placeStatus: placeMutation.status,
    placedOrder: placeMutation.data,
  };
}
