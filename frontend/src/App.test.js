import { render, screen } from '@testing-library/react';
import App from './App';

test('renders loading message initially', () => {
  render(<App />);
  const loadingElement = screen.getByText(/Loading.../i);
  expect(loadingElement).toBeInTheDocument();
});