// Shared read-only business response for isolated browser acceptance fixtures.
export function businessSummary(query, count = 0) {
  const category = { sales_count: 0, sales_value: '0.00', active: 0, expired: 0 }
  return {
    date_from: query.get('date_from'), date_to: query.get('date_to'), mode: query.get('mode') || 'test',
    options: [{ id: 1, name: 'Gym 1' }, { id: 2, name: 'Gym 2' }],
    overall: { visits: count, bookings: count, users: 0, gyms: 2, active_memberships: 0 },
    visits: { individual: count, single_gym: 0, multi_gym: 0, completed: count, upcoming: 0, no_shows: 0, cancelled: 0 },
    collections: { categories: { individual: '0.00', single_gym: '0.00', multi_gym: '0.00' }, total: '0.00', known_dated_total: '0.00', undated_purchases: 0, unattributed_purchases: 0, gym_gross_share: null, fitigo_commission: null, complete: true },
    wallet: { outstanding: '0.00', credits: '0.00', spending: '0.00', cancellation_credits: '0.00' },
    bookings: { total: count, cancelled: 0, no_show: 0, cancellation_rate: 0, no_show_rate: 0 },
    memberships: { categories: { SINGLE_GYM: category, MULTI_GYM: category } },
    customers: { most_active: [] }, gyms: [],
    series: [{ date: query.get('date_from'), individual: count, single_gym: 0, multi_gym: 0, individual_collections: '0.00', single_gym_collections: '0.00', multi_gym_collections: '0.00' }],
    definitions: { collections: 'Verified collections only.', rates: 'Explicit attendance only.' }
  }
}