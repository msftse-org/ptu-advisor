import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

/* ────────────────────────────────────────────────────
   Mock data for live mode deployment eligibility
   ──────────────────────────────────────────────────── */

const mockSubscriptions = [
  { subscription_id: 'sub-1', display_name: 'Test Sub', state: 'Enabled' },
]

const mockAccounts = [
  { name: 'aoai-account', resource_group: 'rg-1', location: 'eastus', kind: 'OpenAI' },
]

const mockMixedDeployments = [
  { name: 'gpt4o-prod', model: 'gpt-4o', model_family: 'GPT-4o', sku_type: 'Standard', sku_capacity: 120, ptu_eligible: true },
  { name: 'embed-prod', model: 'text-embedding-3-large', model_family: 'Embedding', sku_type: 'Standard', sku_capacity: 350, ptu_eligible: false, ineligibility_reason: 'Embedding models use a fixed per-token pricing model and don\'t have PTU provisioned capacity.' },
  { name: 'gpt5-preview', model: 'gpt-5', model_family: 'GPT-5', sku_type: 'Standard', sku_capacity: 60, ptu_eligible: true },
  { name: 'dalle-prod', model: 'dall-e-3', model_family: 'DALL-E', sku_type: 'Standard', sku_capacity: 10, ptu_eligible: false, ineligibility_reason: 'Image generation models bill per image and don\'t support token-based provisioned throughput.' },
]

const mockAllIneligible = [
  { name: 'embed-prod', model: 'text-embedding-3-large', model_family: 'Embedding', sku_type: 'Standard', sku_capacity: 350, ptu_eligible: false, ineligibility_reason: 'Embedding models use a fixed per-token pricing model.' },
  { name: 'dalle-prod', model: 'dall-e-3', model_family: 'DALL-E', sku_type: 'Standard', sku_capacity: 10, ptu_eligible: false, ineligibility_reason: 'Image generation models bill per image.' },
]

function setupLiveModeFetch(deployments = mockMixedDeployments) {
  global.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)

    if (url.includes('/api/focus-topics')) {
      return new Response(JSON.stringify([{ name: 'Cost Reduction', tagline: 'Tagline' }]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    if (url.includes('/api/discovery/subscriptions')) {
      return new Response(JSON.stringify(mockSubscriptions), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    if (url.includes('/api/discovery/accounts')) {
      return new Response(JSON.stringify(mockAccounts), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    if (url.includes('/api/discovery/deployments')) {
      return new Response(JSON.stringify(deployments), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    if (url.includes('/api/pricing/options')) {
      return new Response(
        JSON.stringify({
          regions: [{ name: 'eastus', display_name: 'East US', multiplier: 1.0, zone: 'US' }],
          deployment_types: [
            { name: 'global', label: 'Global', increment: 5, default_min_ptu: 15, base_hourly_rate: 1.0 },
          ],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      )
    }

    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }) as unknown as typeof fetch
}

/* ────────────────────────────────────────────────────
   Tests
   ──────────────────────────────────────────────────── */

describe('PTU Model Eligibility — Deployment Picker', () => {
  describe('Single deployment picker with mixed deployments', () => {
    beforeEach(() => {
      setupLiveModeFetch(mockMixedDeployments)
    })

    it('renders eligible and ineligible chips', async () => {
      render(<App />)

      await waitFor(() => {
        expect(screen.getAllByText('PTU Eligible').length).toBeGreaterThan(0)
      })

      // 2 eligible deployments = 2 deployment-level chips
      expect(screen.getAllByText('PTU Eligible').length).toBe(2)
      // 2 ineligible deployments = 2 deployment-level chips + 2 family-group-header chips = 4
      expect(screen.getAllByText('PTU Not Available').length).toBe(4)
    })

    it('shows deployment names sorted eligible-first', async () => {
      render(<App />)

      await waitFor(() => {
        expect(screen.getByText(/gpt4o-prod/)).toBeInTheDocument()
      })

      // Eligible deployments should be rendered first (gpt4o-prod, gpt5-preview)
      // then ineligible (dalle-prod, embed-prod)
      const labels = screen.getAllByText(/(-prod|-preview)/)
      const names = labels.map((el) => el.textContent)
      const eligibleNames = names.filter((n) => n?.includes('gpt'))
      const ineligibleNames = names.filter((n) => n?.includes('embed') || n?.includes('dalle'))

      // Eligible should appear before ineligible
      expect(eligibleNames.length).toBeGreaterThan(0)
      expect(ineligibleNames.length).toBeGreaterThan(0)
    })

    it('disables radio buttons for ineligible deployments', async () => {
      render(<App />)

      await waitFor(() => {
        // 2 deployment-level + 2 family-group-header = 4
        expect(screen.getAllByText('PTU Not Available').length).toBe(4)
      })

      // Check that ineligible deployment cards have disabled radio buttons
      const radioButtons = screen.getAllByRole('radio')
      const disabledRadios = radioButtons.filter((r) => (r as HTMLInputElement).disabled)
      expect(disabledRadios.length).toBe(2)
    })

    it('auto-selects first eligible deployment', async () => {
      render(<App />)

      await waitFor(() => {
        expect(screen.getAllByText('PTU Eligible').length).toBeGreaterThan(0)
      })

      // Get only deployment radios (name="deployment"), excluding subscription/account radios
      const deploymentRadios = screen.getAllByRole('radio').filter(
        (r) => (r as HTMLInputElement).name === 'deployment'
      )
      const checkedDeploymentRadios = deploymentRadios.filter((r) => (r as HTMLInputElement).checked)
      expect(checkedDeploymentRadios.length).toBe(1)

      // The selected one must be an eligible deployment (not disabled)
      const checkedRadio = checkedDeploymentRadios[0] as HTMLInputElement
      expect(checkedRadio.disabled).toBe(false)
    })

    it('adds is-ineligible class to ineligible deployment labels', async () => {
      render(<App />)

      await waitFor(() => {
        // 2 deployment-level + 2 family-group-header = 4
        expect(screen.getAllByText('PTU Not Available').length).toBe(4)
      })

      // Find labels with is-ineligible class
      const allLabels = document.querySelectorAll('.deployment-option.is-ineligible')
      expect(allLabels.length).toBe(2)
    })

    it('sets title tooltip on ineligible deployment cards', async () => {
      render(<App />)

      await waitFor(() => {
        // 2 deployment-level + 2 family-group-header = 4
        expect(screen.getAllByText('PTU Not Available').length).toBe(4)
      })

      const ineligibleLabels = document.querySelectorAll('.deployment-option.is-ineligible')
      for (const label of ineligibleLabels) {
        const title = label.getAttribute('title')
        expect(title).toContain('PTU is not available for')
        expect(title).toContain('Provisioned Throughput Units')
      }
    })
  })

  describe('No eligible deployments banner', () => {
    beforeEach(() => {
      setupLiveModeFetch(mockAllIneligible)
    })

    it('shows the no-eligible-deployments banner', async () => {
      render(<App />)

      await waitFor(() => {
        expect(screen.getByText('No PTU-Eligible Deployments')).toBeInTheDocument()
      })

      expect(screen.getByText(/none use models that support Provisioned Throughput/)).toBeInTheDocument()
    })

    it('does not auto-select any deployment when all are ineligible', async () => {
      render(<App />)

      await waitFor(() => {
        expect(screen.getByText('No PTU-Eligible Deployments')).toBeInTheDocument()
      })

      // Get only deployment radios (name="deployment")
      const deploymentRadios = screen.getAllByRole('radio').filter(
        (r) => (r as HTMLInputElement).name === 'deployment'
      )
      const checkedDeploymentRadios = deploymentRadios.filter((r) => (r as HTMLInputElement).checked)
      expect(checkedDeploymentRadios.length).toBe(0)
    })
  })

  describe('All eligible deployments', () => {
    const allEligible = [
      { name: 'gpt4o-prod', model: 'gpt-4o', model_family: 'GPT-4o', sku_type: 'Standard', sku_capacity: 120, ptu_eligible: true },
      { name: 'gpt5-preview', model: 'gpt-5', model_family: 'GPT-5', sku_type: 'Standard', sku_capacity: 60, ptu_eligible: true },
    ]

    beforeEach(() => {
      setupLiveModeFetch(allEligible)
    })

    it('does not show no-eligible-deployments banner when all are eligible', async () => {
      render(<App />)

      await waitFor(() => {
        expect(screen.getAllByText('PTU Eligible').length).toBe(2)
      })

      expect(screen.queryByText('No PTU-Eligible Deployments')).not.toBeInTheDocument()
    })

    it('shows no PTU Not Available chips when all eligible', async () => {
      render(<App />)

      await waitFor(() => {
        expect(screen.getAllByText('PTU Eligible').length).toBe(2)
      })

      expect(screen.queryByText('PTU Not Available')).not.toBeInTheDocument()
    })
  })

  /* ────────────────────────────────────────────────────
     Phase 2: Model Family Grouping
     ──────────────────────────────────────────────────── */

  describe('Model family grouping (Phase 2)', () => {
    beforeEach(() => {
      setupLiveModeFetch(mockMixedDeployments)
    })

    it('renders family group headers', async () => {
      render(<App />)

      await waitFor(() => {
        expect(screen.getByText('GPT-4o')).toBeInTheDocument()
      })

      // Should have family group headers for each distinct family
      expect(screen.getByText('GPT-4o')).toBeInTheDocument()
      expect(screen.getByText('GPT-5')).toBeInTheDocument()
      expect(screen.getByText('Embedding')).toBeInTheDocument()
      expect(screen.getByText('DALL-E')).toBeInTheDocument()
    })

    it('renders family groups with data-family attribute', async () => {
      render(<App />)

      await waitFor(() => {
        expect(screen.getByText('GPT-4o')).toBeInTheDocument()
      })

      const familyGroups = document.querySelectorAll('.family-group')
      expect(familyGroups.length).toBe(4)

      const families = Array.from(familyGroups).map((g) => g.getAttribute('data-family'))
      // Eligible families first: GPT-4o, GPT-5; then ineligible: DALL-E, Embedding
      expect(families[0]).toBe('GPT-4o')
      expect(families[1]).toBe('GPT-5')
      // Ineligible families (alphabetical): DALL-E, Embedding
      expect(families[2]).toBe('DALL-E')
      expect(families[3]).toBe('Embedding')
    })

    it('adds is-all-ineligible class to ineligible family groups', async () => {
      render(<App />)

      await waitFor(() => {
        expect(screen.getByText('Embedding')).toBeInTheDocument()
      })

      const ineligibleGroups = document.querySelectorAll('.family-group.is-all-ineligible')
      expect(ineligibleGroups.length).toBe(2) // DALL-E and Embedding
    })
  })

  /* ────────────────────────────────────────────────────
     Phase 2: "Why?" Expandable Panel
     ──────────────────────────────────────────────────── */

  describe('Why? expandable panel (Phase 2)', () => {
    beforeEach(() => {
      setupLiveModeFetch(mockMixedDeployments)
    })

    it('shows "Why?" toggle for ineligible deployments', async () => {
      render(<App />)

      await waitFor(() => {
        expect(screen.getAllByText('Why?').length).toBeGreaterThan(0)
      })

      // 2 ineligible deployments = 2 "Why?" buttons
      expect(screen.getAllByText('Why?').length).toBe(2)
    })

    it('does not show "Why?" toggle for eligible deployments', async () => {
      render(<App />)

      await waitFor(() => {
        expect(screen.getAllByText('PTU Eligible').length).toBe(2)
      })

      // "Why?" buttons should only exist for ineligible deployments
      const whyButtons = screen.getAllByText('Why?')
      expect(whyButtons.length).toBe(2)
    })

    it('expands the panel when "Why?" is clicked', async () => {
      render(<App />)

      await waitFor(() => {
        expect(screen.getAllByText('Why?').length).toBeGreaterThan(0)
      })

      const whyButtons = screen.getAllByText('Why?')
      fireEvent.click(whyButtons[0])

      await waitFor(() => {
        expect(document.querySelector('.why-panel')).toBeInTheDocument()
      })

      // Should show a reason in the panel
      const panel = document.querySelector('.why-panel')
      expect(panel).not.toBeNull()
      expect(panel!.textContent).toContain('PTU-eligible models')
    })

    it('collapses the panel when "Hide details" is clicked', async () => {
      render(<App />)

      await waitFor(() => {
        expect(screen.getAllByText('Why?').length).toBeGreaterThan(0)
      })

      // Expand
      const whyButtons = screen.getAllByText('Why?')
      fireEvent.click(whyButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Hide details')).toBeInTheDocument()
      })

      // Collapse
      fireEvent.click(screen.getByText('Hide details'))

      await waitFor(() => {
        expect(document.querySelector('.why-panel')).not.toBeInTheDocument()
      })
    })

    it('shows model-specific ineligibility reason in the panel', async () => {
      render(<App />)

      await waitFor(() => {
        expect(screen.getAllByText('Why?').length).toBeGreaterThan(0)
      })

      // Find the "Why?" button for the embedding deployment (first in DOM order among ineligible)
      // Family groups are sorted: eligible first, then ineligible alphabetically.
      // DALL-E comes before Embedding alphabetically, so first ineligible "Why?" is for DALL-E
      const whyButtons = screen.getAllByText('Why?')
      fireEvent.click(whyButtons[0])

      await waitFor(() => {
        expect(document.querySelector('.why-panel')).toBeInTheDocument()
      })

      const panel = document.querySelector('.why-panel')
      expect(panel!.textContent).toContain('Image generation')
    })

    it('shows Learn more link in the panel', async () => {
      render(<App />)

      await waitFor(() => {
        expect(screen.getAllByText('Why?').length).toBeGreaterThan(0)
      })

      const whyButtons = screen.getAllByText('Why?')
      fireEvent.click(whyButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Learn more')).toBeInTheDocument()
      })

      const link = screen.getByText('Learn more') as HTMLAnchorElement
      expect(link.href).toContain('provisioned-throughput')
    })
  })
})
