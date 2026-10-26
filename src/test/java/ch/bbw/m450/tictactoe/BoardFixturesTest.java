package ch.bbw.m450.tictactoe;

import static ch.bbw.m450.tictactoe.BoardFixtures.toBoard;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import ch.bbw.m450.tictactoe.TicTacToePlayer.Stone;
import org.junit.jupiter.api.Test;

class BoardFixturesTest {
	@Test
	void toBoardMapsSymbolsToStonesAndEmptyCells() {
		assertThat(toBoard("XXX.O.O.."))
				.containsExactly(Stone.CROSS, Stone.CROSS, Stone.CROSS,
						null, Stone.CIRCLE, null,
						Stone.CIRCLE, null, null);
	}

	@Test
	void toBoardRejectsUnknownSymbols() {
		assertThatThrownBy(() -> toBoard("XOX?....."))
				.isInstanceOf(IllegalArgumentException.class);
	}

	@Test
	void toBoardRejectsWrongLength() {
		assertThatThrownBy(() -> toBoard("XO"))
				.isInstanceOf(IllegalArgumentException.class);
		assertThatThrownBy(() -> toBoard(".........X"))
				.isInstanceOf(IllegalArgumentException.class);
	}
}
